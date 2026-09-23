from __future__ import annotations

import bot
import studio_bot


# Extra first-party studio pages explicitly mentioned under EA in the source brief.
studio_bot.OFFICIAL_PAGES.extend([
    studio_bot.OfficialPage("BioWare", "https://www.bioware.com/news/", weight=5),
    studio_bot.OfficialPage("Battlefield Studios / DICE", "https://www.ea.com/games/battlefield/news", weight=5),
    studio_bot.OfficialPage("Respawn / Apex Legends", "https://www.ea.com/games/apex-legends/news", weight=5),
])

# Some official sites use bot protection against GitHub runners. Keep official-domain
# indexed discovery as a fallback so Epic/Fortnite announcements are still eligible.
OFFICIAL_FALLBACK_SEARCH = [
    bot.Source("Epic Games", "site:epicgames.com/site/en-US/news Epic Games announcement update", weight=5),
    bot.Source("Fortnite", "site:fortnite.com/news Fortnite official news update", weight=5),
]

_original_fetch_stories = bot.fetch_stories


def fetch_stories_with_fallbacks() -> list[bot.Story]:
    stories = _original_fetch_stories()
    for source in OFFICIAL_FALLBACK_SEARCH:
        stories.extend(bot.fetch_source(source))
    return stories


bot.fetch_stories = fetch_stories_with_fallbacks


if __name__ == "__main__":
    raise SystemExit(bot.main())
