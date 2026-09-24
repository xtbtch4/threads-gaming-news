from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import re
import time
from urllib.parse import urljoin, urlsplit

from dateutil import parser as date_parser
from yt_dlp import YoutubeDL

import bot


CYCLE_WINDOW_HOURS = 72

STOPWORDS = {
    "about", "after", "again", "amid", "been", "being", "could", "from", "have",
    "into", "more", "news", "over", "same", "that", "their", "there", "these",
    "they", "this", "those", "through", "under", "week", "with", "within", "would",
    "game", "games", "gaming", "developer", "developers", "director", "company",
    "компания", "игра", "игры", "игровой", "после", "через", "этого", "этой",
    "который", "которая", "стало", "также", "своего", "своей", "новости",
}

SYNONYMS = {
    "restructuring": "restructure",
    "restructured": "restructure",
    "restructure": "restructure",
    "reorganization": "restructure",
    "reorganisation": "restructure",
    "shakeup": "restructure",
    "shake-up": "restructure",
    "layoff": "restructure",
    "layoffs": "restructure",
    "laid": "restructure",
    "fired": "restructure",
    "dismissed": "restructure",
    "cuts": "restructure",
    "cut": "restructure",
    "closure": "restructure",
    "closing": "restructure",
    "закрытие": "restructure",
    "сокращения": "restructure",
    "сокращение": "restructure",
    "уволен": "restructure",
    "увольнение": "restructure",
    "реструктуризации": "restructure",
    "реструктуризация": "restructure",
    "studios": "studio",
    "studio": "studio",
    "студии": "studio",
    "студия": "studio",
    "microsoft": "xbox",
    "revamp": "update",
    "revamped": "update",
    "revamping": "update",
    "overhaul": "update",
    "overhauled": "update",
    "overhauling": "update",
    "roadmap": "update",
    "roadmaps": "update",
    "plans": "update",
    "planned": "update",
    "planning": "update",
    "evolve": "update",
    "evolves": "update",
    "evolved": "update",
    "evolution": "update",
    "refresh": "update",
    "refreshed": "update",
    "changes": "update",
    "changed": "update",
    "changing": "update",
}

CONTEXT_TOKENS = {
    "restructure", "acquisition", "merger", "delay", "cancel", "shutdown",
    "release", "launch", "update", "expansion", "dlc", "trailer", "showcase",
}

GENERIC = {
    "xbox", "playstation", "nintendo", "steam", "studio", "activision",
    "bethesda", "ubisoft", "blizzard", "electronic", "arts", "restructure",
}

GAMEPLAY_HINTS = {
    "gameplay", "game-play", "gameplay footage", "in-game", "ingame", "walkthrough",
    "playthrough", "combat footage", "game footage", "demo gameplay", "gameplay demo",
    "геймплей", "игровой процесс", "демонстрация геймплея", "кадры геймплея",
}

VIDEO_BY_STORY: dict[str, str] = {}
CURRENT_STORY_URL = ""
CURRENT_VIDEO_URL = ""


def tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zа-яё0-9][a-zа-яё0-9-]{2,}", (text or "").casefold())
    result: set[str] = set()
    for token in raw:
        token = SYNONYMS.get(token, token)
        if len(token) < 3 or token in STOPWORDS:
            continue
        result.add(token)
    return result


def item_text(item: dict) -> str:
    return " ".join(str(item.get(key) or "") for key in (
        "title", "title_ru", "threads_teaser_ru", "event_key"
    ))


def item_time(item: dict) -> datetime | None:
    for key in ("telegram_published_at", "published_at_source", "threads_published_at"):
        value = item.get(key)
        if not value:
            continue
        try:
            parsed = date_parser.parse(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
    return None


def same_news_cycle(story: bot.Story, item: dict) -> bool:
    published = item_time(item)
    if published and datetime.now(timezone.utc) - published > timedelta(hours=CYCLE_WINDOW_HOURS):
        return False

    new_tokens = tokens(f"{story.title} {story.summary}")
    old_tokens = tokens(item_text(item))
    common = new_tokens & old_tokens
    if not common:
        return False

    context_shared = bool(common & CONTEXT_TOKENS)
    specific_common = {t for t in common if t not in GENERIC and t not in CONTEXT_TOKENS}
    anchor_common = {t for t in common if t in GENERIC}

    if context_shared and len(specific_common | anchor_common) >= 3:
        return True
    if "restructure" in common and len(common) >= 3:
        return True

    denominator = max(1, min(len(new_tokens), len(old_tokens)))
    return len(common) / denominator >= 0.48 and len(common) >= 4


_original_known_story = bot.known_story


def known_story_with_cycle(story: bot.Story, state: dict) -> bool:
    if _original_known_story(story, state):
        return True
    for item in state.get("items", []):
        if same_news_cycle(story, item):
            bot.LOG.info("Skipped same news cycle: %s ~ %s", story.title, item.get("title"))
            return True
    return False


def complete_sentence(text: str, limit: int) -> str:
    text = bot.clean_text(text).rstrip(" .…")
    if len(text) <= limit:
        return text + "." if text and text[-1] not in "!?" else text

    chunk = text[:limit].rstrip()
    candidates = [chunk.rfind(mark) for mark in (". ", "! ", "? ")]
    end = max(candidates)
    if end >= max(120, limit // 2):
        return chunk[: end + 1].rstrip()
    if " " in chunk:
        chunk = chunk.rsplit(" ", 1)[0]
    return chunk.rstrip(" ,;:-.") + "."


def telegram_text_complete(rendered: bot.Rendered, story: bot.Story) -> str:
    title = f"🎮 {bot.clean_text(rendered.title_ru).rstrip(' .…')}"
    source = f"Источник: {story.source}\n{story.url}"
    fixed = len(title) + len(source) + 4
    quote = ""
    if rendered.quote_ru:
        speaker = f" — {rendered.speaker_ru}" if rendered.speaker_ru else ""
        quote = f"«{bot.clean_text(rendered.quote_ru).rstrip(' .…')}»{speaker}"

    reserve_quote = len(quote) + 2 if quote else 0
    summary_budget = max(260, 970 - fixed - reserve_quote)
    summary = complete_sentence(rendered.telegram_summary_ru, summary_budget)

    parts = [title, summary]
    candidate = "\n\n".join(parts + ([quote] if quote else []) + [source])
    if len(candidate) <= 990:
        return candidate

    candidate = "\n\n".join(parts + [source])
    if len(candidate) <= 990:
        return candidate

    summary_budget = max(180, 990 - fixed)
    summary = complete_sentence(rendered.telegram_summary_ru, summary_budget)
    return "\n\n".join([title, summary, source])


def has_gameplay_hint(text: str) -> bool:
    lowered = html.unescape(text or "").casefold()
    return any(hint in lowered for hint in GAMEPLAY_HINTS)


def video_quality_score(url: str, context: str = "") -> int:
    text = f"{url} {context}".casefold()
    score = 0
    for marker, points in (("2160", 500), ("4k", 500), ("1440", 400), ("1080", 300), ("720", 200), ("480", 100)):
        if marker in text:
            score = max(score, points)
    if ".mp4" in urlsplit(url).path.casefold() or ".mp4" in url.casefold():
        score += 50
    if has_gameplay_hint(context) or has_gameplay_hint(url):
        score += 1000
    return score


def _clean_media_url(value: str, base_url: str) -> str:
    value = html.unescape((value or "").replace("\\/", "/")).strip().strip("'\"")
    if not value or value.startswith(("data:", "blob:")):
        return ""
    return urljoin(base_url, value)


def _best_progressive_from_ytdlp(url: str, story: bot.Story) -> tuple[str, int]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 12,
        "extractor_retries": 1,
        "retries": 1,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        bot.LOG.info("Video extractor skipped %s: %s", url, str(exc).splitlines()[0])
        return "", 0

    if isinstance(info, dict) and info.get("entries"):
        entries = [entry for entry in info.get("entries", []) if isinstance(entry, dict)]
        if entries:
            info = entries[0]
    if not isinstance(info, dict):
        return "", 0

    info_text = " ".join(str(info.get(key) or "") for key in ("title", "description", "webpage_url"))
    combined = f"{story.title} {story.summary} {info_text}"
    if not has_gameplay_hint(combined):
        return "", 0

    formats = []
    for fmt in info.get("formats", []) or []:
        if not isinstance(fmt, dict) or not fmt.get("url"):
            continue
        if fmt.get("vcodec") in (None, "none") or fmt.get("acodec") in (None, "none"):
            continue
        protocol = str(fmt.get("protocol") or "")
        direct = str(fmt.get("url") or "")
        if not direct.startswith(("http://", "https://")) or "m3u8" in protocol:
            continue
        formats.append(fmt)

    if formats:
        formats.sort(
            key=lambda f: (
                1 if str(f.get("ext") or "").casefold() == "mp4" else 0,
                int(f.get("height") or 0),
                int(f.get("width") or 0),
                float(f.get("tbr") or 0),
                int(f.get("filesize") or f.get("filesize_approx") or 0),
            ),
            reverse=True,
        )
        best = formats[0]
        height = int(best.get("height") or 0)
        return str(best.get("url")), 1200 + height

    direct = str(info.get("url") or "")
    if direct.startswith(("http://", "https://")):
        return direct, 1100 + int(info.get("height") or 0)
    return "", 0


def discover_gameplay_video(story: bot.Story) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GamingNewsBot/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        response = bot.requests.get(story.url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()
    except bot.requests.RequestException as exc:
        bot.LOG.info("Gameplay video page unavailable: %s", str(exc).splitlines()[0])
        return ""

    if "html" not in response.headers.get("content-type", "").casefold():
        return ""
    page = response.text[:1_500_000]
    base_url = response.url
    page_has_gameplay = has_gameplay_hint(f"{story.title} {story.summary} {page[:250000]}")

    direct_candidates: list[tuple[int, str]] = []
    extractor_candidates: list[str] = []

    attr_re = r"(?:src|content|href)\s*=\s*['\"]([^'\"]+)['\"]"
    for match in re.finditer(r"<(?:video|source|iframe|meta)\b[^>]*>", page, flags=re.I):
        tag = match.group(0)
        values = re.findall(attr_re, tag, flags=re.I)
        if not values:
            continue
        context = page[max(0, match.start() - 500): min(len(page), match.end() + 500)]
        relevant = page_has_gameplay or has_gameplay_hint(context)
        for raw in values:
            url = _clean_media_url(raw, base_url)
            if not url:
                continue
            low = url.casefold()
            if any(host in low for host in ("youtube.com", "youtu.be", "vimeo.com", "twitch.tv")):
                if relevant:
                    extractor_candidates.append(url)
                continue
            if any(ext in low for ext in (".mp4", "/video/", "video=")) and relevant:
                direct_candidates.append((video_quality_score(url, context), url))

    for key in ("og:video:secure_url", "og:video:url", "og:video", "twitter:player:stream"):
        value = bot.meta_content(page, key)
        url = _clean_media_url(value, base_url)
        if url and page_has_gameplay:
            if any(host in url.casefold() for host in ("youtube.com", "youtu.be", "vimeo.com")):
                extractor_candidates.append(url)
            else:
                direct_candidates.append((video_quality_score(url, story.title), url))

    for match in re.finditer(r'"(?:contentUrl|content_url|videoUrl|video_url)"\s*:\s*"([^"]+)"', page, flags=re.I):
        raw = match.group(1)
        context = page[max(0, match.start() - 400): min(len(page), match.end() + 400)]
        if not (page_has_gameplay or has_gameplay_hint(context)):
            continue
        url = _clean_media_url(raw, base_url)
        if url:
            direct_candidates.append((video_quality_score(url, context), url))

    best_url = ""
    best_score = 0
    for candidate in dict.fromkeys(extractor_candidates):
        resolved, score = _best_progressive_from_ytdlp(candidate, story)
        if resolved and score > best_score:
            best_url, best_score = resolved, score

    if page_has_gameplay and not best_url:
        resolved, score = _best_progressive_from_ytdlp(story.url, story)
        if resolved and score > best_score:
            best_url, best_score = resolved, score

    if direct_candidates:
        score, url = max(direct_candidates, key=lambda item: item[0])
        if score > best_score:
            best_url, best_score = url, score

    if best_url:
        bot.LOG.info("Gameplay video selected (quality score %d): %s", best_score, best_url)
    return best_url


_original_fetch_article_context = bot.fetch_article_context


def fetch_article_context_with_video(story: bot.Story):
    global CURRENT_STORY_URL, CURRENT_VIDEO_URL
    result = _original_fetch_article_context(story)
    CURRENT_STORY_URL = story.url
    try:
        CURRENT_VIDEO_URL = discover_gameplay_video(story)
    except Exception as exc:
        bot.LOG.info("Gameplay video detection failed: %s", str(exc).splitlines()[0])
        CURRENT_VIDEO_URL = ""
    VIDEO_BY_STORY[story.url] = CURRENT_VIDEO_URL
    return result


_original_publish_telegram = bot.publish_telegram


def publish_telegram_with_gameplay(rendered: bot.Rendered, story: bot.Story, image_url: str):
    video_url = VIDEO_BY_STORY.get(story.url, "")
    if bot.DRY_RUN:
        if video_url:
            bot.LOG.info("DRY RUN preferred Telegram media: gameplay video %s", video_url)
        return _original_publish_telegram(rendered, story, image_url)

    if video_url:
        token, chat_id, public_username = bot.telegram_config()
        full = bot.telegram_text(rendered, story)
        try:
            result = bot.telegram_call(
                token,
                "sendVideo",
                {
                    "chat_id": chat_id,
                    "video": video_url,
                    "caption": full[:1024],
                    "supports_streaming": True,
                },
            )
            message_id = str(result.get("result", {}).get("message_id", ""))
            if public_username and message_id:
                return message_id, f"https://t.me/{public_username}/{message_id}"
            funnel = bot.os.getenv("TELEGRAM_FUNNEL_URL", "").strip()
            if funnel:
                return message_id or "unknown", funnel
        except RuntimeError as exc:
            bot.LOG.warning("Telegram gameplay video failed; using image fallback: %s", exc)

    return _original_publish_telegram(rendered, story, image_url)


_original_publish_threads = bot.publish_threads


def publish_threads_with_gameplay(teaser: str, telegram_url: str, image_url: str = "") -> str:
    video_url = CURRENT_VIDEO_URL
    if not video_url:
        return _original_publish_threads(teaser, telegram_url, image_url)

    text = bot.threads_post_text(teaser, telegram_url)
    if bot.DRY_RUN:
        bot.LOG.info("DRY RUN Threads prefers gameplay video:\n%s\nVideo: %s", text, video_url)
        return "dry-run"

    try:
        token = bot.threads_config()
        profile = bot.requests.get(
            "https://graph.threads.net/v1.0/me",
            params={"fields": "id", "access_token": token},
            timeout=30,
        )
        profile_data = profile.json()
        if not profile.ok or not profile_data.get("id"):
            raise RuntimeError(f"Threads profile failed: {profile.text[:400]}")
        user_id = str(profile_data["id"])

        create = bot.requests.post(
            f"https://graph.threads.net/v1.0/{user_id}/threads",
            data={
                "media_type": "VIDEO",
                "video_url": video_url,
                "text": text,
                "access_token": token,
            },
            timeout=40,
        )
        created = create.json()
        if not create.ok or not created.get("id"):
            raise RuntimeError(f"Threads video create failed: {create.text[:400]}")

        last_error = None
        for delay in (2, 3, 5, 8, 13, 21):
            time.sleep(delay)
            finish = bot.requests.post(
                f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                data={"creation_id": created["id"], "access_token": token},
                timeout=40,
            )
            data = finish.json()
            if finish.ok and data.get("id"):
                return str(data["id"])
            last_error = data
            err = data.get("error", {}) if isinstance(data, dict) else {}
            retryable = err.get("is_transient") is True or err.get("code") in {2, 24} or err.get("error_subcode") == 4279009
            if not retryable:
                break
        raise RuntimeError(f"Threads gameplay video publish failed: {str(last_error)[:300]}")
    except Exception as exc:
        bot.LOG.warning("Threads gameplay video failed; using image/text fallback: %s", str(exc).splitlines()[0])
        return _original_publish_threads(teaser, telegram_url, image_url)


_original_save_state = bot.save_state


def save_state_with_video(state: dict) -> None:
    if CURRENT_STORY_URL and CURRENT_VIDEO_URL:
        for item in reversed(state.get("items", [])):
            if bot.canonical_url(str(item.get("url", ""))) == bot.canonical_url(CURRENT_STORY_URL):
                item["video_url"] = CURRENT_VIDEO_URL
                break
    _original_save_state(state)


_original_retry_pending_threads = bot.retry_pending_threads


def retry_pending_threads_with_video(state: dict) -> None:
    global CURRENT_STORY_URL, CURRENT_VIDEO_URL
    for item in state.get("items", []):
        if item.get("telegram_message_id") and not item.get("threads_id") and item.get("threads_teaser_ru") and item.get("telegram_url"):
            CURRENT_STORY_URL = str(item.get("url") or "")
            CURRENT_VIDEO_URL = str(item.get("video_url") or "")
            break
    _original_retry_pending_threads(state)


bot.known_story = known_story_with_cycle
bot.telegram_text = telegram_text_complete
bot.fetch_article_context = fetch_article_context_with_video
bot.publish_telegram = publish_telegram_with_gameplay
bot.publish_threads = publish_threads_with_gameplay
bot.save_state = save_state_with_video
bot.retry_pending_threads = retry_pending_threads_with_video

if __name__ == "__main__":
    raise SystemExit(bot.main())
