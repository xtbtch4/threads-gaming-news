from __future__ import annotations

import re

import bot


# Strong gaming signals. A mixed-media outlet story with at least one of these can still pass.
_GAME_TERMS = (
    "video game", "videogame", "gameplay", "gaming", " game ", " games ",
    "playstation", "ps5", "ps4", "xbox", "nintendo", "switch", "steam", "pc game",
    "developer", "development studio", "publisher", "dlc", "expansion", "patch", "update",
    "console", "controller", "gpu", "graphics card", "esports", "e-sports",
    "видеоигр", "игров", "геймплей", "playstation", "xbox", "nintendo", "steam",
    "разработчик", "студия", "издатель", "дополнение", "патч", "консоль", "видеокарт",
)

# Signals that a story is about general entertainment rather than games.
_ENTERTAINMENT_TERMS = (
    "tv series", "television series", "series is", "season", "episode", "streaming", "stream free",
    "free on streaming", "movie", "film", "box office", "netflix", "hulu", "disney+", "disney plus",
    "prime video", "max streaming", "pluto tv", "paramount+", "paramount plus", "peacock",
    "actor", "actress", "cast member", "cult classic", "sci-fi series", "spy thriller",
    "сериал", "сезон", "эпизод", "серия сериала", "стриминг", "бесплатного просмотра",
    "фильм", "кино", "актёр", "актер", "актриса", "телесериал",
)


def _normalized(story: bot.Story) -> str:
    return f" {story.title} {story.summary} {story.url} ".casefold()


def _has_game_signal(text: str) -> bool:
    return any(term in text for term in _GAME_TERMS)


def _entertainment_score(text: str) -> int:
    return sum(1 for term in _ENTERTAINMENT_TERMS if term in text)


def _obvious_non_gaming_entertainment(story: bot.Story) -> bool:
    text = _normalized(story)
    if _has_game_signal(text):
        return False

    score = _entertainment_score(text)
    if score >= 2:
        return True

    # Catch obvious TV/streaming slugs even if RSS summaries are very short.
    path = story.url.casefold()
    if any(marker in path for marker in ("stream-free", "streaming", "tv-series", "movie", "film")):
        if score >= 1:
            return True

    # Common title forms from mixed gaming/entertainment outlets.
    title = story.title.casefold()
    if re.search(r"\b(series|season|episode|movie|film)\b", title) and score >= 1:
        return True
    return False


_original_fetch_stories = bot.fetch_stories


def fetch_stories_gaming_only() -> list[bot.Story]:
    stories = _original_fetch_stories()
    filtered: list[bot.Story] = []
    removed = 0
    for story in stories:
        if _obvious_non_gaming_entertainment(story):
            removed += 1
            bot.LOG.info("Blocked non-gaming entertainment story: %s (%s)", story.title, story.source)
            continue
        filtered.append(story)
    if removed:
        bot.LOG.info("Gaming relevance filter removed %d non-gaming stories", removed)
    return filtered


bot.fetch_stories = fetch_stories_gaming_only
