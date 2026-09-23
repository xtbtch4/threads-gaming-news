from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser

import bot


@dataclass(frozen=True)
class DirectFeed:
    name: str
    url: str
    weight: int


DIRECT_FEEDS = [
    DirectFeed("IGN", "https://www.ign.com/rss/v2/articles/feed?categories=games", 3),
    DirectFeed("GameSpot", "https://www.gamespot.com/feeds/mashup/", 3),
    DirectFeed("PC Gamer", "https://www.pcgamer.com/rss/", 3),
    DirectFeed("Eurogamer", "https://www.eurogamer.net/feed", 3),
    DirectFeed("Polygon", "https://www.polygon.com/rss/index.xml", 2),
    DirectFeed("Rock Paper Shotgun", "https://www.rockpapershotgun.com/feed/news", 2),
    DirectFeed("PlayStation Blog", "https://blog.playstation.com/feed/", 4),
    DirectFeed("Xbox Wire", "https://news.xbox.com/en-us/feed/", 4),
    DirectFeed("StopGame", "https://rss.stopgame.ru/rss_news.xml", 2),
]


def fetch_direct_feed(source: DirectFeed) -> list[bot.Story]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=bot.MAX_AGE_HOURS)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GamingNewsBot/1.0)",
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
    }
    stories: list[bot.Story] = []
    try:
        response = bot.requests.get(source.url, headers=headers, timeout=18, allow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        for entry in feed.entries[:60]:
            published = bot.entry_date(entry)
            if not published or published < cutoff or published > now + timedelta(hours=2):
                continue
            title = bot.clean_text(str(entry.get("title") or ""))
            raw_url = str(entry.get("link") or "").strip()
            if not title or not raw_url.startswith(("http://", "https://")):
                continue
            url = bot.canonical_url(raw_url)
            summary = bot.clean_text(str(entry.get("summary") or entry.get("description") or title))
            score = bot.importance(title, summary, source.weight, published)
            stories.append(
                bot.Story(
                    title=title,
                    url=url,
                    source=source.name,
                    published=published,
                    summary=summary,
                    score=score,
                    fingerprint=bot.fingerprint(title),
                    image_url=bot.entry_image(entry),
                )
            )
        bot.LOG.info("Direct RSS %s: %d fresh stories", source.name, len(stories))
    except Exception as exc:
        bot.LOG.info("Direct RSS unavailable %s: %s", source.name, str(exc).splitlines()[0])
    return stories


_original_fetch_stories = bot.fetch_stories


def fetch_stories_with_direct_rss() -> list[bot.Story]:
    result = _original_fetch_stories()
    for source in DIRECT_FEEDS:
        result.extend(fetch_direct_feed(source))
    return result


bot.fetch_stories = fetch_stories_with_direct_rss
