from __future__ import annotations

import os
import re

import bot
import run_bot
import studio_bot


# Extra first-party studio pages explicitly mentioned under EA in the source brief.
studio_bot.OFFICIAL_PAGES.extend([
    # EA's main homepage currently exposes the newest corporate/game articles more
    # reliably to server-side crawlers than /news on GitHub runners.
    studio_bot.OfficialPage("Electronic Arts Home", "https://www.ea.com/", weight=5),
    studio_bot.OfficialPage("BioWare", "https://www.bioware.com/news/", weight=5),
    studio_bot.OfficialPage("Battlefield Studios / DICE", "https://www.ea.com/games/battlefield/news", weight=5),
    studio_bot.OfficialPage("Respawn / Apex Legends", "https://www.ea.com/games/apex-legends/apex-legends/news", weight=5),
])

# Some official sites either block GitHub runners or render news cards in a way that
# the direct HTML parser cannot reliably discover. Keep indexed discovery restricted
# to first-party domains so official announcements are still eligible.
OFFICIAL_FALLBACK_SEARCH = [
    bot.Source("Electronic Arts", "site:ea.com/news Electronic Arts game news announcement update", weight=5),
    bot.Source("Respawn / Apex Legends", "site:ea.com/games/apex-legends/apex-legends/news Apex Legends official news update", weight=5),
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


MAJOR_EVENT_TERMS = (
    "closure", "close down", "shut down", "shutdown", "layoff", "layoffs",
    "acquisition", "acquire", "acquired", "cancelled", "canceled", "cancellation",
    "delay", "delayed", "release date", "закрытие", "закрыть", "увольнен", "увольнён",
    "сокращения", "поглощение", "отмена", "отменена", "перенос", "дата выхода",
)


def _major_event(story: bot.Story) -> bool:
    text = f"{story.title} {story.summary}".casefold()
    return any(term in text for term in MAJOR_EVENT_TERMS)


# Make every rejection visible in Actions logs. "Fresh" only means that an item is
# inside the 72-hour source window; it may still be already published or low-value.
# Major industry events get a narrow one-point exception so studio closures, layoffs,
# acquisitions, cancellations and release-date delays are not lost at score 4.
# For those events, use the original duplicate test (same URL/title), not the broad
# cross-story news-cycle test: Ninja Theory closing is distinct from Halo layoffs even
# though both belong to the same Xbox restructuring.
def select_stories_verbose(stories, state):
    selected: list[bot.Story] = []
    for story in sorted(stories, key=lambda s: (s.score, s.published), reverse=True):
        major_exception = story.score == bot.MIN_SCORE - 1 and _major_event(story)
        if story.score < bot.MIN_SCORE and not major_exception:
            bot.LOG.info("Skipped low score %d < %d: %s", story.score, bot.MIN_SCORE, story.title)
            continue
        if major_exception:
            bot.LOG.info("Major-event exception %d -> %d: %s", story.score, bot.MIN_SCORE, story.title)
            already_known = run_bot._original_known_story(story, state)
        else:
            already_known = bot.known_story(story, state)
        if already_known:
            bot.LOG.info("Skipped already published/deduped: %s", story.title)
            continue
        if any(bot.similar_tokens(story.title, other.title) >= 0.62 for other in selected):
            bot.LOG.info("Skipped duplicate within current run: %s", story.title)
            continue
        bot.LOG.info("Eligible new story score=%d source=%s: %s", story.score, story.source, story.title)
        selected.append(story)
        if len(selected) >= max(bot.MAX_POSTS * 5, bot.MAX_POSTS):
            break
    return selected


bot.select_stories = select_stories_verbose


def _sentence_excerpt(text: str, limit: int) -> str:
    text = bot.clean_text(text)
    if not text:
        return ""
    if len(text) <= limit:
        return text if text[-1:] in ".!?" else text + "."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chosen: list[str] = []
    total = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        extra = len(sentence) + (1 if chosen else 0)
        if chosen and total + extra > limit:
            break
        if not chosen and len(sentence) > limit:
            cut = sentence[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-.")
            return cut + "."
        chosen.append(sentence)
        total += extra
        if total >= limit * 0.72:
            break
    result = " ".join(chosen).strip()
    if not result:
        result = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-.") + "."
    elif result[-1:] not in ".!?":
        result += "."
    return result


def _fallback_render(story: bot.Story) -> tuple[bot.Rendered, str]:
    # Keep the channel alive when both Gemini projects are rate-limited or unavailable.
    # Facts still come only from the source article. The fallback keeps the source
    # language instead of inventing/guessing a translation.
    evidence, image_url, _quotes = bot.fetch_article_context(story)
    title = bot.clean_text(story.title)
    base = bot.clean_text(story.summary) or bot.clean_text(evidence) or title
    summary = _sentence_excerpt(base, 720)
    teaser = _sentence_excerpt(base, 280)

    words = re.findall(r"[a-z0-9]{3,}", title.casefold())[:10]
    event_key = " ".join(words) if words else f"fallback {story.fingerprint}"
    rendered = bot.Rendered(
        title_ru=title,
        telegram_summary_ru=summary,
        threads_teaser_ru=teaser,
        event_key=event_key,
    )
    bot.LOG.warning("Using source-language fallback because all Gemini projects are unavailable: %s", title)
    return rendered, image_url


_original_rewrite_story = bot.rewrite_story


def _is_gemini_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "Gemini" in message or "gemini" in message


def rewrite_story_resilient(story: bot.Story) -> tuple[bot.Rendered, str]:
    try:
        return _original_rewrite_story(story)
    except RuntimeError as first_exc:
        if not _is_gemini_error(first_exc):
            raise

        primary = os.getenv("GEMINI_API_KEY", "").strip()
        secondary = os.getenv("GEMINI_API_KEY_2", "").strip()
        if secondary and secondary != primary:
            bot.LOG.warning("Primary Gemini project unavailable; trying GEMINI_API_KEY_2")
            previous = os.environ.get("GEMINI_API_KEY")
            os.environ["GEMINI_API_KEY"] = secondary
            try:
                result = _original_rewrite_story(story)
                bot.LOG.info("Secondary Gemini project succeeded")
                return result
            except RuntimeError as second_exc:
                if not _is_gemini_error(second_exc):
                    raise
                bot.LOG.warning("Secondary Gemini project unavailable: %s", str(second_exc).splitlines()[0])
            finally:
                if previous is None:
                    os.environ.pop("GEMINI_API_KEY", None)
                else:
                    os.environ["GEMINI_API_KEY"] = previous

        return _fallback_render(story)


bot.rewrite_story = rewrite_story_resilient


def threads_post_text_link_only(teaser: str, telegram_url: str) -> str:
    suffix = f"\n\n{telegram_url}"
    room = max(40, 500 - len(suffix))
    return f"{bot.shorten(teaser, room)}{suffix}"[:500]


bot.threads_post_text = threads_post_text_link_only


if __name__ == "__main__":
    raise SystemExit(bot.main())
