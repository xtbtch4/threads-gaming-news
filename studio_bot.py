from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import re
from urllib.parse import urljoin, urlsplit

from dateutil import parser as date_parser

import bot


@dataclass(frozen=True)
class OfficialPage:
    name: str
    url: str
    weight: int = 5


OFFICIAL_PAGES = [
    OfficialPage("Rockstar Games", "https://www.rockstargames.com/newswire"),
    OfficialPage("CD Projekt RED", "https://press.cdprojektred.com/en/news"),
    OfficialPage("Naughty Dog", "https://www.naughtydog.com/blog"),
    OfficialPage("Bethesda", "https://bethesda.net/en-US/news?author=bethesda"),
    OfficialPage("Valve / Counter-Strike", "https://store.steampowered.com/news/app/730"),
    OfficialPage("Valve / Dota 2", "https://store.steampowered.com/news/app/570"),
    OfficialPage("FromSoftware", "https://www.fromsoftware.jp/ww/?mode=0"),
    OfficialPage("Nintendo", "https://www.nintendo.com/us/whatsnew/"),
    OfficialPage("Capcom", "https://news.capcomusa.com/"),
    OfficialPage("Kojima Productions", "https://www.kojimaproductions.jp/en/news"),
    OfficialPage("GSC Game World", "https://www.stalker2.com/news"),
    OfficialPage("4A Games", "https://www.4a-games.com.mt/4a-dna"),
    OfficialPage("Frogwares", "https://support.frogwares.com/", weight=4),
    OfficialPage("Electronic Arts", "https://www.ea.com/news"),
    OfficialPage("Epic Games / Fortnite", "https://www.fortnite.com/news"),
    OfficialPage("Unreal Engine", "https://www.unrealengine.com/en-US/news", weight=4),
    OfficialPage("Ubisoft", "https://www.ubisoft.com/en-us/news"),
]

GENERIC_LINK_TEXT = {
    "read more", "more", "learn more", "view", "view all", "news", "home", "games",
    "support", "store", "about", "careers", "privacy", "press", "latest", "next", "previous",
}

DATE_REGEXES = [
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+20\d{2}\b",
    r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2}\b",
    r"\b20\d{2}[-./]\d{1,2}[-./]\d{1,2}\b",
]

ARTICLE_PATH_HINTS = (
    "/news/", "/newswire/", "/blog/", "/blogs/", "/whatsnew/", "/article/", "/articles/",
    "/press/", "/updates/", "/update/",
)


def _strip_tags(value: str) -> str:
    return bot.clean_text(html.unescape(value or ""))


def _parse_date(value: str) -> datetime | None:
    text = _strip_tags(value)
    text = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    for pattern in DATE_REGEXES:
        for match in re.findall(pattern, text, flags=re.I):
            try:
                parsed = date_parser.parse(match, fuzzy=False)
            except (ValueError, TypeError, OverflowError):
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    return None


def _same_site(candidate: str, landing: str) -> bool:
    a = urlsplit(candidate).netloc.casefold().removeprefix("www.")
    b = urlsplit(landing).netloc.casefold().removeprefix("www.")
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _article_priority(url: str, title: str) -> int:
    path = urlsplit(url).path.casefold()
    score = 0
    if any(hint in path for hint in ARTICLE_PATH_HINTS):
        score += 10
    if re.search(r"/20\d{2}/|/\d{4}/\d{1,2}/", path):
        score += 3
    if len(title) >= 32:
        score += 1
    return score


def _article_meta(url: str) -> tuple[datetime | None, str, str, str]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GamingNewsBot/1.0)", "Accept": "text/html"}
    try:
        response = bot.requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
    except bot.requests.RequestException:
        return None, "", "", ""
    if "html" not in response.headers.get("content-type", "").casefold():
        return None, "", "", ""
    page = response.text[:900_000]

    published = None
    for key in ("article:published_time", "date", "datePublished", "publish-date", "pubdate"):
        raw = bot.meta_content(page, key)
        if not raw:
            continue
        try:
            published = date_parser.parse(raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
            break
        except (ValueError, TypeError, OverflowError):
            pass
    if published is None:
        match = re.search(r'<time\b[^>]*datetime=["\']([^"\']+)["\']', page, flags=re.I)
        if match:
            try:
                published = date_parser.parse(match.group(1))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                published = published.astimezone(timezone.utc)
            except (ValueError, TypeError, OverflowError):
                published = None
    if published is None:
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page, flags=re.I)
        if match:
            try:
                published = date_parser.parse(match.group(1))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                published = published.astimezone(timezone.utc)
            except (ValueError, TypeError, OverflowError):
                published = None

    title = bot.meta_content(page, "og:title") or bot.meta_content(page, "twitter:title")
    summary = bot.meta_content(page, "og:description") or bot.meta_content(page, "description")
    image = bot.meta_content(page, "og:image") or bot.meta_content(page, "twitter:image")
    return published, _strip_tags(title), _strip_tags(summary), urljoin(response.url, image) if image else ""


def fetch_official_page(source: OfficialPage) -> list[bot.Story]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=bot.MAX_AGE_HOURS)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GamingNewsBot/1.0)", "Accept": "text/html"}
    try:
        response = bot.requests.get(source.url, headers=headers, timeout=18, allow_redirects=True)
        response.raise_for_status()
    except bot.requests.RequestException as exc:
        bot.LOG.info("Official source unavailable %s: %s", source.name, str(exc).splitlines()[0])
        return []
    if "html" not in response.headers.get("content-type", "").casefold():
        return []

    page = response.text[:1_500_000]
    candidates: list[tuple[int, str, str, datetime | None]] = []
    seen: set[str] = set()
    anchor_re = re.compile(r'<a\b([^>]*?)href=["\']([^"\']+)["\']([^>]*)>(.*?)</a>', re.I | re.S)
    for match in anchor_re.finditer(page):
        href = html.unescape(match.group(2)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        url = urljoin(response.url, href)
        if not url.startswith(("http://", "https://")) or not _same_site(url, response.url):
            continue
        canonical = bot.canonical_url(url)
        if canonical in seen or canonical == bot.canonical_url(response.url):
            continue
        title = _strip_tags(match.group(4))
        title_key = title.casefold().strip(" .:—-")
        if len(title) < 18 or title_key in GENERIC_LINK_TEXT:
            continue
        low_url = canonical.casefold()
        if any(part in low_url for part in ("/privacy", "/terms", "/careers", "/login", "/account")):
            continue

        published = _parse_date(title) or _parse_date(match.group(0))
        candidates.append((_article_priority(canonical, title), title, canonical, published))
        seen.add(canonical)
        if len(candidates) >= 120:
            break

    candidates.sort(key=lambda item: item[0], reverse=True)

    stories: list[bot.Story] = []
    detail_lookups = 0
    for _priority, title, url, published in candidates:
        if published is not None and published < cutoff:
            continue

        final_title = title
        summary = title
        image = ""

        if detail_lookups < 8:
            detail_lookups += 1
            meta_date, meta_title, meta_summary, meta_image = _article_meta(url)
            if meta_date is not None:
                published = meta_date
            final_title = meta_title or final_title
            summary = meta_summary or summary
            image = meta_image

        if published is None or published < cutoff or published > now + timedelta(hours=2):
            continue
        score = bot.importance(final_title, summary, source.weight, published)
        if score < bot.MIN_SCORE:
            continue
        stories.append(
            bot.Story(
                title=final_title,
                url=url,
                source=source.name,
                published=published,
                summary=summary,
                score=score,
                fingerprint=bot.fingerprint(final_title),
                image_url=image,
            )
        )
    bot.LOG.info("Official source %s: %d fresh stories", source.name, len(stories))
    return stories


# run_bot adds semantic/news-cycle dedupe, complete Telegram captions and
# preference for the highest-quality gameplay video available.
import run_bot  # noqa: E402,F401

_original_fetch_stories = bot.fetch_stories


def fetch_stories_with_official() -> list[bot.Story]:
    result: list[bot.Story] = []
    for source in OFFICIAL_PAGES:
        result.extend(fetch_official_page(source))
    result.extend(_original_fetch_stories())
    return result


bot.fetch_stories = fetch_stories_with_official


if __name__ == "__main__":
    raise SystemExit(bot.main())
