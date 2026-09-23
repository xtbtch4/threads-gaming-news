from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from dateutil import parser as date_parser

import bot


CYCLE_WINDOW_HOURS = 72

STOPWORDS = {
    "about", "after", "again", "amid", "been", "being", "could", "from", "have",
    "into", "more", "news", "over", "same", "that", "their", "there", "these",
    "they", "this", "those", "through", "under", "week", "with", "within", "would",
    "game", "games", "gaming", "developer", "developers", "director", "company",
    "компания", "игра", "игры", "игровой", "после", "через", "этого", "этой",
    "который", "которая", "стало", "также", "своего", "своей", "новости",
}

SYNONYMS = {
    "restructuring": "restructure",
    "restructured": "restructure",
    "restructure": "restructure",
    "reorganization": "restructure",
    "reorganisation": "restructure",
    "shakeup": "restructure",
    "shake-up": "restructure",
    "layoff": "restructure",
    "layoffs": "restructure",
    "laid": "restructure",
    "fired": "restructure",
    "dismissed": "restructure",
    "cuts": "restructure",
    "cut": "restructure",
    "closure": "restructure",
    "closing": "restructure",
    "закрытие": "restructure",
    "сокращения": "restructure",
    "сокращение": "restructure",
    "уволен": "restructure",
    "увольнение": "restructure",
    "реструктуризации": "restructure",
    "реструктуризация": "restructure",
    "studios": "studio",
    "studio": "studio",
    "студии": "studio",
    "студия": "studio",
    "microsoft": "xbox",
}

CONTEXT_TOKENS = {
    "restructure", "acquisition", "merger", "delay", "cancel", "shutdown",
    "release", "launch", "update", "expansion", "dlc", "trailer", "showcase",
}

GENERIC = {
    "xbox", "playstation", "nintendo", "steam", "studio", "activision",
    "bethesda", "ubisoft", "blizzard", "electronic", "arts", "restructure",
}


def tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zа-яё0-9][a-zа-яё0-9-]{2,}", (text or "").casefold())
    result: set[str] = set()
    for token in raw:
        token = SYNONYMS.get(token, token)
        if len(token) < 3 or token in STOPWORDS:
            continue
        result.add(token)
    return result


def item_text(item: dict) -> str:
    return " ".join(str(item.get(key) or "") for key in (
        "title", "title_ru", "threads_teaser_ru", "event_key"
    ))


def item_time(item: dict) -> datetime | None:
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


def same_news_cycle(story: bot.Story, item: dict) -> bool:
    published = item_time(item)
    if published and datetime.now(timezone.utc) - published > timedelta(hours=CYCLE_WINDOW_HOURS):
        return False

    new_tokens = tokens(f"{story.title} {story.summary}")
    old_tokens = tokens(item_text(item))
    common = new_tokens & old_tokens
    if not common:
        return False

    # Require a shared event context plus at least two shared anchors/entities.
    context_shared = bool(common & CONTEXT_TOKENS)
    specific_common = {t for t in common if t not in GENERIC and t not in CONTEXT_TOKENS}
    anchor_common = {t for t in common if t in GENERIC}

    if context_shared and len(specific_common | anchor_common) >= 3:
        return True

    # Catch very obvious franchise/platform follow-ups in the same short news cycle.
    if "restructure" in common and len(common) >= 3:
        return True

    # High token overlap is still a strong duplicate signal even with different wording.
    denominator = max(1, min(len(new_tokens), len(old_tokens)))
    return len(common) / denominator >= 0.48 and len(common) >= 4


_original_known_story = bot.known_story


def known_story_with_cycle(story: bot.Story, state: dict) -> bool:
    if _original_known_story(story, state):
        return True
    for item in state.get("items", []):
        if same_news_cycle(story, item):
            bot.LOG.info("Skipped same news cycle: %s ~ %s", story.title, item.get("title"))
            return True
    return False


def complete_sentence(text: str, limit: int) -> str:
    text = bot.clean_text(text).rstrip(" .…")
    if len(text) <= limit:
        return text + "." if text and text[-1] not in "!?" else text

    chunk = text[:limit].rstrip()
    # Prefer ending on a complete sentence.
    candidates = [chunk.rfind(mark) for mark in (". ", "! ", "? ")]
    end = max(candidates)
    if end >= max(120, limit // 2):
        return chunk[: end + 1].rstrip()

    # Otherwise end at a word boundary and close with a period, never with ellipsis.
    if " " in chunk:
        chunk = chunk.rsplit(" ", 1)[0]
    return chunk.rstrip(" ,;:-.") + "."


def telegram_text_complete(rendered: bot.Rendered, story: bot.Story) -> str:
    title = f"🎮 {bot.clean_text(rendered.title_ru).rstrip(' .…')}"
    source = f"Источник: {story.source}\n{story.url}"

    # Telegram photo captions are limited to 1024 chars. Keep a safety margin so the
    # whole post, including source URL, stays in a single photo message.
    fixed = len(title) + len(source) + 4
    quote = ""
    if rendered.quote_ru:
        speaker = f" — {rendered.speaker_ru}" if rendered.speaker_ru else ""
        quote = f"«{bot.clean_text(rendered.quote_ru).rstrip(' .…')}»{speaker}"

    reserve_quote = len(quote) + 2 if quote else 0
    summary_budget = max(260, 970 - fixed - reserve_quote)
    summary = complete_sentence(rendered.telegram_summary_ru, summary_budget)

    parts = [title, summary]
    candidate = "\n\n".join(parts + ([quote] if quote else []) + [source])
    if len(candidate) <= 990:
        return candidate

    # Drop the optional quote before cutting useful news context.
    candidate = "\n\n".join(parts + [source])
    if len(candidate) <= 990:
        return candidate

    summary_budget = max(180, 990 - fixed)
    summary = complete_sentence(rendered.telegram_summary_ru, summary_budget)
    return "\n\n".join([title, summary, source])


bot.known_story = known_story_with_cycle
bot.telegram_text = telegram_text_complete

if __name__ == "__main__":
    raise SystemExit(bot.main())
