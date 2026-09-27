from __future__ import annotations

import re

import bot


_original_rewrite_story = bot.rewrite_story


def _has_cyrillic(value: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value or ""))


def rewrite_story_require_russian(story: bot.Story):
    rendered, image_url = _original_rewrite_story(story)
    title = getattr(rendered, "title_ru", "")
    summary = getattr(rendered, "telegram_summary_ru", "")
    if not _has_cyrillic(title) or not _has_cyrillic(summary):
        bot.LOG.warning(
            "Gemini-only translation failed; skipping story without publishing source language: %s",
            story.title,
        )
        raise RuntimeError("Russian translation unavailable after all allowed Gemini Lite keys")
    return rendered, image_url


bot.rewrite_story = rewrite_story_require_russian
