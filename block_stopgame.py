from __future__ import annotations

from urllib.parse import urlsplit

import bot
import direct_feeds


# Remove StopGame from every known collector layer.
bot.SOURCES[:] = [
    source for source in bot.SOURCES
    if source.name.casefold() != "stopgame" and "stopgame.ru" not in source.query.casefold()
]

direct_feeds.DIRECT_FEEDS[:] = [
    source for source in direct_feeds.DIRECT_FEEDS
    if source.name.casefold() != "stopgame" and "stopgame.ru" not in source.url.casefold()
]


_original_fetch_stories = bot.fetch_stories


def _is_stopgame(story: bot.Story) -> bool:
    if story.source.casefold() == "stopgame":
        return True
    try:
        host = urlsplit(story.url).netloc.casefold()
    except Exception:
        return False
    return host == "stopgame.ru" or host.endswith(".stopgame.ru")


def fetch_stories_without_stopgame() -> list[bot.Story]:
    stories = _original_fetch_stories()
    filtered = [story for story in stories if not _is_stopgame(story)]
    removed = len(stories) - len(filtered)
    if removed:
        bot.LOG.info("Blocked %d StopGame stories", removed)
    return filtered


bot.fetch_stories = fetch_stories_without_stopgame
