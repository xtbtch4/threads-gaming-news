from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from dateutil import parser as date_parser

import bot
import run_bot


WINDOW_HOURS = 72

SYNONYMS = {
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
    "patch": "update",
    "hotfix": "update",
    "updates": "update",
    "updated": "update",
    "announces": "announce",
    "announced": "announce",
    "announcement": "announce",
    "reveals": "announce",
    "revealed": "announce",
    "unveils": "announce",
    "unveiled": "announce",
}

CONTEXT_TOKENS = {
    "update", "announce", "release", "launch", "delay", "cancel", "shutdown",
    "acquisition", "merger", "expansion", "dlc", "trailer", "showcase",
    "restructure",
}

# Words that are often capitalized merely because they occur in a headline but do
# not identify a game, company, person or franchise.
NON_ENTITY_TOKENS = {
    "officially", "official", "massive", "major", "large", "big", "new", "mode",
    "first", "final", "future", "year", "years", "march", "october", "december",
    "today", "tomorrow", "could", "make", "break", "coming", "comes", "gets",
    "getting", "adds", "added", "more", "less", "made", "using", "use", "used",
    "game", "games", "gaming", "studio", "studios", "developer", "developers",
    "players", "player", "system", "feature", "features", "story", "end", "lineup",
    "exclusive", "great", "stronger", "easier", "challenge", "returns", "return",
    "continue", "continues", "carry", "forward", "catch", "version", "everything",
    "reveals", "revealed", "announces", "announced", "unveils", "unveiled",
    "the", "and", "but", "not", "for", "from", "into", "with", "while", "still",
    "even", "just", "only", "some", "than", "that", "this", "what", "when", "where",
    "which", "will", "would", "its", "has", "have", "had", "who", "why", "how",
}

STOPWORDS = {
    "about", "after", "again", "amid", "been", "being", "from", "have", "into",
    "over", "same", "that", "their", "there", "these", "they", "this", "those",
    "through", "under", "week", "with", "within", "would", "will", "than", "what",
    "when", "where", "which", "while", "your", "just", "only", "some", "them",
}


def _tokens(text: str) -> set[str]:
    text = (text or "").replace("_", " ").casefold()
    raw = re.findall(r"[a-zа-яё0-9][a-zа-яё0-9-]{2,}", text)
    result: set[str] = set()
    for token in raw:
        token = SYNONYMS.get(token, token)
        if token in STOPWORDS:
            continue
        result.add(token)
    return result


def _headline_entities(title: str) -> set[str]:
    entities: set[str] = set()
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'-]{1,}", title or ""):
        canonical = SYNONYMS.get(raw.casefold(), raw.casefold())
        if canonical in CONTEXT_TOKENS or canonical in NON_ENTITY_TOKENS or canonical in STOPWORDS:
            continue
        # Proper names/acronyms/numerical franchise markers are useful anchors.
        if raw[0].isupper() or raw.isupper() or any(ch.isdigit() for ch in raw):
            entities.add(canonical)
    return entities


def _item_time(item: dict) -> datetime | None:
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


def _same_cross_source_event(story: bot.Story, item: dict) -> bool:
    published = _item_time(item)
    if published and datetime.now(timezone.utc) - published > timedelta(hours=WINDOW_HOURS):
        return False

    new_entities = _headline_entities(story.title)
    old_entities = _headline_entities(str(item.get("title") or ""))
    old_event_tokens = _tokens(str(item.get("event_key") or ""))

    # A generated event_key may contain a company/franchise omitted from one outlet's
    # headline, so allow it to confirm entities that are explicitly present in the new
    # headline. It cannot introduce arbitrary generic body words.
    shared_entities = new_entities & (old_entities | old_event_tokens)
    if len(shared_entities) < 2:
        return False

    # Event/action compatibility must come from the headline/event-key layer. This
    # prevents two different stories about the same game from being merged merely
    # because both article bodies mention an update somewhere.
    new_actions = _tokens(story.title) & CONTEXT_TOKENS
    old_actions = _tokens(
        f"{item.get('title') or ''} {item.get('event_key') or ''}"
    ) & CONTEXT_TOKENS
    if not (new_actions & old_actions):
        return False

    return True


_original_known_story = run_bot._original_known_story


def known_story_strict(story: bot.Story, state: dict) -> bool:
    if _original_known_story(story, state):
        return True

    for item in state.get("items", []):
        if _same_cross_source_event(story, item):
            bot.LOG.info(
                "Skipped strict cross-source duplicate: %s ~ %s",
                story.title,
                item.get("title"),
            )
            return True
    return False


def event_seen_strict(event_key: str, state: dict) -> bool:
    new_tokens = _tokens(event_key)
    new_actions = new_tokens & CONTEXT_TOKENS
    for item in state.get("items", []):
        old_key = str(item.get("event_key") or "")
        if not old_key:
            continue
        old_tokens = _tokens(old_key)
        shared = (new_tokens & old_tokens) - CONTEXT_TOKENS - NON_ENTITY_TOKENS
        if len(shared) >= 2 and new_actions & (old_tokens & CONTEXT_TOKENS):
            return True
        if bot.event_similarity(event_key, old_key) >= 0.60:
            return True
    return False


bot.known_story = known_story_strict
bot.event_seen = event_seen_strict
