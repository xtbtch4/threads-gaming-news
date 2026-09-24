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

    # Different outlets often describe the same game update using very different
    # headline vocabulary. Normalize the common editorial variants so a roadmap,
    # revamp or overhaul of the same title is treated as one news cycle.
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

    # Require a shared event/action plus several concrete anchors. This catches
    # cross-source rewrites such as "Marathon roadmap" vs "Marathon revamp" while
    # still allowing genuinely different stories about the same game to pass.
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
            ),
            reverse=True,
        )
        best = formats[0]
        direct = str(best.get("url") or "")
        height = int(best.get("height") or 0)
        quality = height + (1000 if has_gameplay_hint(combined) else 0)
        return direct, quality
    return "", 0


def _candidate_media_urls(page: str, base_url: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    patterns = [
        r'<video\b[^>]*(?:src|data-src)=["\']([^"\']+)["\'][^>]*>',
        r'<source\b[^>]*src=["\']([^"\']+)["\'][^>]*>',
        r'<meta\b[^>]*(?:property|name)=["\'](?:og:video(?::secure_url)?|twitter:player:stream)["\'][^>]*content=["\']([^"\']+)["\'][^>]*>',
        r'"(?:contentUrl|embedUrl|videoUrl|video_url|mp4|src)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'https?://[^"\'<>\\\s]+\.mp4(?:\?[^"\'<>\\\s]*)?',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page, re.I | re.S):
            value = match.group(1) if match.groups() else match.group(0)
            url = _clean_media_url(value, base_url)
            if not url:
                continue
            start = max(0, match.start() - 500)
            end = min(len(page), match.end() + 500)
            context = bot.clean_text(page[start:end])
            candidates.append((url, context))
    return candidates


def find_gameplay_video(story: bot.Story) -> str:
    global CURRENT_STORY_URL, CURRENT_VIDEO_URL
    cached = VIDEO_BY_STORY.get(story.fingerprint, "")
    if cached:
        CURRENT_STORY_URL = story.url
        CURRENT_VIDEO_URL = cached
        return cached

    try:
        response = bot.requests.get(story.url, headers=bot.HTTP_HEADERS, timeout=20)
        response.raise_for_status()
        page = response.text
        base_url = response.url
    except Exception as exc:
        bot.LOG.info("Gameplay video page unavailable: %s", str(exc).splitlines()[0])
        CURRENT_STORY_URL = story.url
        CURRENT_VIDEO_URL = ""
        return ""

    scored: list[tuple[int, str]] = []
    for url, context in _candidate_media_urls(page, base_url):
        quality = video_quality_score(url, context)
        if has_gameplay_hint(context) or has_gameplay_hint(url):
            quality += 1000
        scored.append((quality, url))

    ytdlp_url, ytdlp_quality = _best_progressive_from_ytdlp(story.url, story)
    if ytdlp_url:
        scored.append((ytdlp_quality + 1000, ytdlp_url))

    if not scored:
        CURRENT_STORY_URL = story.url
        CURRENT_VIDEO_URL = ""
        return ""

    scored.sort(reverse=True)
    quality, video_url = scored[0]
    if quality < 1000:
        bot.LOG.info("No clearly identified gameplay video found for: %s", story.title)
        CURRENT_STORY_URL = story.url
        CURRENT_VIDEO_URL = ""
        return ""

    VIDEO_BY_STORY[story.fingerprint] = video_url
    CURRENT_STORY_URL = story.url
    CURRENT_VIDEO_URL = video_url
    bot.LOG.info("Gameplay video selected (quality score %s): %s", quality, video_url)
    return video_url


_original_rewrite_story = bot.rewrite_story


def rewrite_story_with_video(story: bot.Story):
    rendered, image_url = _original_rewrite_story(story)
    find_gameplay_video(story)
    return rendered, image_url


bot.known_story = known_story_with_cycle
bot.telegram_post_text = telegram_text_complete
bot.rewrite_story = rewrite_story_with_video


_original_save_state = bot.save_state


def save_state_with_video(state: dict) -> None:
    if CURRENT_STORY_URL and CURRENT_VIDEO_URL:
        for item in reversed(state.get("items", [])):
            if bot.canonical_url(str(item.get("url", ""))) == bot.canonical_url(CURRENT_STORY_URL):
                item["video_url"] = CURRENT_VIDEO_URL
                break
    _original_save_state(state)


bot.save_state = save_state_with_video


_original_retry_pending_threads = bot.retry_pending_threads


def retry_pending_threads_safe(state: dict) -> None:
    try:
        _original_retry_pending_threads(state)
    except RuntimeError as exc:
        bot.LOG.warning("Pending Threads retry skipped: %s", exc)


bot.retry_pending_threads = retry_pending_threads_safe


if __name__ == "__main__":
    raise SystemExit(bot.main())
