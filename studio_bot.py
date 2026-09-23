from __future__ import annotations

import bot


# Official developer/publisher sources get a higher weight than press outlets.
# Bing News RSS is used as the discovery layer; the final article is fetched
# from the studio's own domain and goes through the normal dedupe/media pipeline.
OFFICIAL_STUDIO_SOURCES = [
    bot.Source("Rockstar Games", "site:rockstargames.com/newswire Rockstar Games GTA Grand Theft Auto Red Dead", weight=5),
    bot.Source("CD Projekt RED", "site:press.cdprojektred.com/en/news CD Projekt RED Witcher Cyberpunk", weight=5),
    bot.Source("Naughty Dog", "site:naughtydog.com/blog Naughty Dog The Last of Us Uncharted Intergalactic", weight=5),
    bot.Source("Bethesda", "site:bethesda.net/en-US/news Bethesda Elder Scrolls Fallout Starfield", weight=5),
    bot.Source("Valve", "site:store.steampowered.com/news Valve Half-Life Counter-Strike Dota Steam", weight=5),
    bot.Source("FromSoftware", "site:fromsoftware.jp Elden Ring Duskbloods Armored Core FromSoftware", weight=5),
    bot.Source("Nintendo", "site:nintendo.com games news announcement Nintendo", weight=5),
    bot.Source("Capcom", "site:capcom-games.com Resident Evil Monster Hunter Street Fighter Devil May Cry Capcom", weight=5),
    bot.Source("Kojima Productions", "site:kojimaproductions.jp/en/news Kojima Productions Death Stranding PHYSINT", weight=5),
    bot.Source("GSC Game World", "site:gsc-game.com STALKER GSC Game World news", weight=5),
    bot.Source("4A Games", "site:4a-games.com.mt/4a-dna 4A Games Metro news", weight=5),
    bot.Source("Frogwares", "site:frogwares.com Frogwares Sinking City Sherlock Holmes news", weight=5),
    bot.Source("Frogwares Support", "site:support.frogwares.com Sinking City patch notes gameplay update", weight=4),
    bot.Source("Electronic Arts", "site:ea.com/news Electronic Arts EA games news update", weight=5),
    bot.Source("Epic Games", "site:epicgames.com/site/en-US/news Epic Games Fortnite Unreal Engine news", weight=5),
    bot.Source("Ubisoft", "site:ubisoft.com/en-us/news Ubisoft Assassin's Creed Far Cry Rainbow Six news", weight=5),
]


def install_official_sources() -> None:
    # Replace same-name base sources (notably Nintendo) and put official sources first.
    official_names = {source.name for source in OFFICIAL_STUDIO_SOURCES}
    remaining = [source for source in bot.SOURCES if source.name not in official_names]
    bot.SOURCES = OFFICIAL_STUDIO_SOURCES + remaining
    bot.LOG.info("Installed %d official studio sources; %d total sources", len(OFFICIAL_STUDIO_SOURCES), len(bot.SOURCES))


install_official_sources()

# Import after source installation: run_bot adds dedupe, complete captions and
# high-quality gameplay-video preference on top of the base bot.
import run_bot  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(bot.main())
