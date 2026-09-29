from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import unicodedata

from dateutil import parser as date_parser

import bot
import run_bot


WINDOW_HOURS = 48

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
    "announcements": "announce",
    "reveals": "announce",
    "revealed": "announce",
    "reveal": "announce",
    "unveils": "announce",
    "unveiled": "announce",
    "unveil": "announce",
    "presents": "announce",
    "presented": "announce",
    "presentation": "announce",
    "present": "announce",
    "showcases": "announce",
    "showcased": "announce",
    "showcase": "announce",
    "demonstrates": "announce",
    "demonstrated": "announce",
    "demonstration": "announce",
    "confirms": "announce",
    "confirmed": "announce",
    "confirmation": "announce",
    "details": "announce",
    "detailed": "announce",
    "discloses": "announce",
    "disclosed": "announce",
    "shares": "announce",
    "shared": "announce",
    "costs": "cost",
    "costing": "cost",
    "priced": "price",
    "prices": "price",
    "payments": "payment",
    "paying": "payment",
    "paid": "payment",
    "funded": "funding",
    "funds": "funding",
    "funding": "funding",
    "budgets": "budget",
    "millions": "million",
    "launch": "release",
    "launches": "release",
    "launched": "release",
    "launching": "release",
    "releases": "release",
    "released": "release",
    "releasing": "release",
    "delays": "delay",
    "delayed": "delay",
    "postponed": "delay",
    "postpones": "delay",
    "cancels": "cancel",
    "canceled": "cancel",
    "cancelled": "cancel",
    "acquires": "acquisition",
    "acquired": "acquisition",
    "buys": "acquisition",
    "bought": "acquisition",
    "merges": "merger",
    "merged": "merger",
    "closes": "shutdown",
    "closed": "shutdown",
    "shuts": "shutdown",
    "layoffs": "restructure",
    "layoff": "restructure",
    "restructuring": "restructure",
    "restructured": "restructure",
}

CONTEXT_TOKENS = {
    "update", "announce", "release", "launch", "delay", "cancel", "shutdown",
    "acquisition", "merger", "expansion", "dlc", "trailer", "showcase",
    "restructure",
}

BUDGET_TOKENS = {
    "budget", "cost", "price", "payment", "funding", "million", "billion",
    "spend", "spending", "finance", "financing", "fund",
}

NON_ENTITY_TOKENS = {
    "officially", "official", "massive", "major", "large", "big", "new", "mode",
    "first", "final", "future", "year", "years", "march", "october", "december",
    "january", "february", "april", "may", "june", "july", "august", "september",
    "november", "today", "tomorrow", "could", "make", "break", "coming", "comes",
    "gets", "getting", "adds", "added", "more", "less", "made", "using", "use",
    "used", "game", "games", "gaming", "studio", "studios", "developer",
    "developers", "players", "player", "system", "feature", "features", "story",
    "end", "lineup", "exclusive", "great", "stronger", "easier", "challenge",
    "returns", "return", "continue", "continues", "carry", "forward", "catch",
    "version", "everything", "full", "fully", "complete", "project", "projects",
    "news", "information", "details", "detail", "report", "reports", "says", "said",
    "according", "about", "around", "during", "ahead", "behind",
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

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass(frozen=True)
class EventFingerprint:
    digest: str
    entities: frozenset[str]
    actions: frozenset[str]
    topics: frozenset[str]
    years: frozenset[str]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    return normalized.replace("_", " ").replace("’", "'")


def _canonical_token(token: str) -> str:
    token = _normalize_text(token).casefold()
    if token.endswith("'s") and len(token) > 3:
        token = token[:-2]
    return SYNONYMS.get(token, token)


def _tokens(text: str) -> set[str]:
    text = _normalize_text(text).casefold()
    raw = re.findall(r"[a-zа-яё0-9][a-zа-яё0-9'-]{2,}", text)
    result: set[str] = set()
    for token in raw:
        token = _canonical_token(token)
        if token in STOPWORDS:
            continue
        result.add(token)
    return result


def _headline_entities(title: str) -> set[str]:
    entities: set[str] = set()
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'’-]{1,}", title or ""):
        canonical = _canonical_token(raw)
        if (
            canonical in CONTEXT_TOKENS
            or canonical in BUDGET_TOKENS
            or canonical in NON_ENTITY_TOKENS
            or canonical in STOPWORDS
        ):
            continue
        if raw[0].isupper() or raw.isupper() or any(ch.isdigit() for ch in raw):
            entities.add(canonical)
    return entities


def _event_fingerprint(text: str) -> EventFingerprint:
    tokens = _tokens(text)
    years = frozenset(YEAR_RE.findall(_normalize_text(text)))
    actions = frozenset(tokens & CONTEXT_TOKENS)
    topics = frozenset(tokens & BUDGET_TOKENS)
    entities = frozenset(
        token
        for token in tokens
        if token not in CONTEXT_TOKENS
        and token not in BUDGET_TOKENS
        and token not in NON_ENTITY_TOKENS
        and token not in years
    )
    payload = "|".join(
        (
            ",".join(sorted(actions)),
            ",".join(sorted(entities)),
            ",".join(sorted(topics)),
            ",".join(sorted(years)),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return EventFingerprint(digest, entities, actions, topics, years)


def _fingerprints_match(new: EventFingerprint, old: EventFingerprint) -> bool:
    if new.digest == old.digest:
        return True

    shared_entities = new.entities & old.entities
    if len(shared_entities) < 2:
        return False

    if new.years and old.years and not (new.years & old.years):
        return False

    if new.topics and old.topics:
        return True

    denominator = max(1, min(len(new.entities), len(old.entities)))
    entity_overlap = len(shared_entities) / denominator

    shared_actions = new.actions & old.actions
    if shared_actions:
        if len(shared_entities) >= 3:
            return True
        return len(shared_entities) >= 2 and entity_overlap >= 0.75

    if (not new.actions or not old.actions) and new.years and old.years and (new.years & old.years):
        return len(shared_entities) >= 3 and entity_overlap >= 0.70

    return False


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


def _within_window(item: dict) -> bool:
    published = _item_time(item)
    if published is None:
        return False
    age = datetime.now(timezone.utc) - published
    return timedelta(0) <= age <= timedelta(hours=WINDOW_HOURS)


def _same_cross_source_event(story: bot.Story, item: dict) -> bool:
    if not _within_window(item):
        return False

    old_text = f"{item.get('title') or ''} {item.get('event_key') or ''}"
    new_fp = _event_fingerprint(story.title)
    old_fp = _event_fingerprint(old_text)
    if _fingerprints_match(new_fp, old_fp):
        return True

    new_entities = _headline_entities(story.title)
    old_entities = _headline_entities(str(item.get("title") or ""))
    old_event_tokens = _tokens(str(item.get("event_key") or ""))
    shared_entities = new_entities & (old_entities | old_event_tokens)
    if len(shared_entities) < 3:
        return False

    new_tokens = _tokens(story.title)
    old_tokens = _tokens(old_text)

    if (new_tokens & BUDGET_TOKENS) and (old_tokens & BUDGET_TOKENS):
        return True

    new_actions = new_tokens & CONTEXT_TOKENS
    old_actions = old_tokens & CONTEXT_TOKENS
    return bool(new_actions & old_actions)


_original_known_story = run_bot._original_known_story


def known_story_strict(story: bot.Story, state: dict) -> bool:
    if _original_known_story(story, state):
        return True

    for item in state.get("items", []):
        if _same_cross_source_event(story, item):
            bot.LOG.info(
                "Skipped 48h event-fingerprint duplicate: %s ~ %s",
                story.title,
                item.get("title"),
            )
            return True
    return False


def event_seen_strict(event_key: str, state: dict) -> bool:
    new_fp = _event_fingerprint(event_key)
    for item in state.get("items", []):
        if not _within_window(item):
            continue
        old_key = str(item.get("event_key") or "")
        if not old_key:
            continue

        old_fp = _event_fingerprint(old_key)
        if _fingerprints_match(new_fp, old_fp):
            bot.LOG.info(
                "Skipped duplicate event fingerprint %s ~ %s",
                new_fp.digest,
                old_fp.digest,
            )
            return True

        if bot.event_similarity(event_key, old_key) >= 0.64:
            return True
    return False


bot.known_story = known_story_strict
bot.event_seen = event_seen_strict
