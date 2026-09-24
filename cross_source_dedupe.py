from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from dateutil import parser as date_parser

import bot
import run_bot


WINDOW_HOURS = 72

# Normalize different editorial wording for the same kind of event. The important
# restriction is below: a shared action alone is never enough to mark a duplicate.
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

# These words are too generic to count as the concrete identity of an event.
BROAD_TOKENS = {
    "officially", "official", "massive", "major", "large", "big", "new", "mode",
    "first", "future", "year", "years", "march", "october", "december", "today",
    "tomorrow", "could", "make", "break", "coming", "gets", "getting", "adds",
    "added", "more", "game", "games", "gaming", "studio", "studios", "developer",
    "developers", "players", "player", "system", "feature", "features",
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

    # Identity anchors deliberately come from headlines/event_key, not the whole
    # article body. This prevents unrelated stories from matching just because two
    # summaries both contain generic words such as "update", "players" or "mode".
    new_anchor_tokens = _tokens(story.title)
    old_anchor_tokens = _tokens(
        f"{item.get('title') or ''} {item.get('event_key') or ''}"
    )
    shared_identity = (
        new_anchor_tokens & old_anchor_tokens
    ) - CONTEXT_TOKENS - BROAD_TOKENS

    # Require at least two concrete shared identifiers, e.g. Bungie + Marathon.
    # One franchise/company token by itself is not enough.
    if len(shared_identity) < 2:
        return False

    new_full = _tokens(f"{story.title} {story.summary}")
    old_full = _tokens(" ".join(str(item.get(key) or "") for key in (
        "title", "title_ru", "threads_teaser_ru", "event_key"
    )))
    common = new_full & old_full

    # The same concrete entities must also share the type of event/action.
    if common & CONTEXT_TOKENS:
        return True

    # For incidents whose headline wording contains no explicit action synonym,
    # accept only a very strong overlap, still anchored by two specific entities.
    denominator = max(1, min(len(new_full), len(old_full)))
    return len(common) >= 6 and len(common) / denominator >= 0.60


# Bypass run_bot's older broad cycle matcher while preserving exact URL,
# fingerprint and title-similarity checks from bot.py.
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


bot.known_story = known_story_strict
