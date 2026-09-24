from __future__ import annotations

from urllib.parse import urlsplit

import bot
import direct_feeds


# Remove PC Gamer from every known collector layer.
bot.SOURCES[:] = [
    source for source in bot.SOURCES
    if source.name.casefold() != "pc gamer" and "pcgamer.com" not in source.query.casefold()
]

direct_feeds.DIRECT_FEEDS[:] = [
    source for source in direct_feeds.DIRECT_FEEDS
    if source.name.casefold() != "pc gamer" and "pcgamer.com" not in source.url.casefold()
]


_original_fetch_stories = bot.fetch_stories


def _is_pcgamer(story: bot.Story) -> bool:
    if story.source.casefold() == "pc gamer":
        return True
    try:
        host = urlsplit(story.url).netloc.casefold()
    except Exception:
        return False
    return host == "pcgamer.com" or host.endswith(".pcgamer.com")


def fetch_stories_without_pcgamer() -> list[bot.Story]:
    stories = _original_fetch_stories()
    filtered = [story for story in stories if not _is_pcgamer(story)]
    removed = len(stories) - len(filtered)
    if removed:
        bot.LOG.info("Blocked %d PC Gamer stories", removed)
    return filtered


bot.fetch_stories = fetch_stories_without_pcgamer
