from __future__ import annotations

import re

import bot


# Gemini occasionally produces a one-off typo/hallucination in a quoted title while
# using the correct title consistently in the summary/teaser. Prefer the repeated
# form from the body when it clearly refers to the same quoted work.
_QUOTE_RE = re.compile(r"[«\"]([^»\"]{3,120})[»\"]")
_STOP = {
    "и", "в", "на", "с", "по", "для", "из", "к", "о", "об", "от", "до", "за",
    "the", "a", "an", "of", "and", "to", "for", "in", "on", "with",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]{3,}", (text or "").casefold())
        if token not in _STOP
    }


def _same_work_hint(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    common = ta & tb
    # One shared distinctive word is enough only for short two-part titles such as
    # «...: Финал» where the body repeats the alternative consistently.
    if len(common) >= 2:
        return True
    if len(common) == 1 and min(len(ta), len(tb)) <= 2:
        return True
    return False


def _correct_inconsistent_title(rendered: bot.Rendered) -> bot.Rendered:
    title_quotes = _QUOTE_RE.findall(rendered.title_ru or "")
    if not title_quotes:
        return rendered

    body_text = f"{rendered.telegram_summary_ru}\n{rendered.threads_teaser_ru}"
    body_quotes = _QUOTE_RE.findall(body_text)
    if not body_quotes:
        return rendered

    counts: dict[str, int] = {}
    original_case: dict[str, str] = {}
    for phrase in body_quotes:
        key = phrase.casefold().strip()
        counts[key] = counts.get(key, 0) + 1
        original_case.setdefault(key, phrase.strip())

    new_title = rendered.title_ru
    changed = False
    for wrong in title_quotes:
        wrong_key = wrong.casefold().strip()
        if counts.get(wrong_key, 0) > 0:
            continue
        candidates = [
            (count, original_case[key])
            for key, count in counts.items()
            if count >= 2 and _same_work_hint(wrong, original_case[key])
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item[0], len(_tokens(item[1]))), reverse=True)
        replacement = candidates[0][1]
        new_title = new_title.replace(f"«{wrong}»", f"«{replacement}»")
        new_title = new_title.replace(f'"{wrong}"', f'"{replacement}"')
        bot.LOG.warning("Corrected inconsistent generated title: %s -> %s", wrong, replacement)
        changed = True

    if not changed:
        return rendered
    return bot.Rendered(
        title_ru=new_title,
        telegram_summary_ru=rendered.telegram_summary_ru,
        threads_teaser_ru=rendered.threads_teaser_ru,
        event_key=rendered.event_key,
        quote_original=rendered.quote_original,
        quote_ru=rendered.quote_ru,
        speaker_ru=rendered.speaker_ru,
    )


_original_rewrite_story = bot.rewrite_story


def rewrite_story_with_title_guard(story: bot.Story):
    rendered, image_url = _original_rewrite_story(story)
    return _correct_inconsistent_title(rendered), image_url


bot.rewrite_story = rewrite_story_with_title_guard
