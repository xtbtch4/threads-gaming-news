from __future__ import annotations

import re

import bot


_original_telegram_text = bot.telegram_text

_STOP = {
    "после", "перед", "через", "среди", "также", "когда", "который", "которая", "которые",
    "компания", "компании", "студия", "студии", "система", "системы", "новый", "новая", "новые",
    "with", "after", "before", "from", "that", "this", "their", "company", "studio", "system", "new",
}


def _stem(token: str) -> str:
    token = token.casefold().replace("ё", "е")
    # Lightweight stemming is enough for headline/body duplicate detection.
    for suffix in (
        "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ией", "ией", "иях",
        "ость", "ости", "ение", "ения", "ений", "ировать", "ирует", "ировали",
        "ами", "ями", "ов", "ев", "ей", "ой", "ий", "ый", "ая", "ое", "ые", "ую", "юю",
        "ам", "ям", "ах", "ях", "ом", "ем", "а", "я", "ы", "и", "у", "ю", "е",
        "ing", "ed", "es", "s",
    ):
        if len(token) >= 7 and token.endswith(suffix):
            token = token[:-len(suffix)]
            break
    return token


def _tokens(text: str) -> set[str]:
    result: set[str] = set()
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{4,}", text or ""):
        stem = _stem(raw)
        if stem and stem not in _STOP and len(stem) >= 4:
            result.add(stem)
    return result


def _first_sentence(text: str) -> tuple[str, str]:
    text = bot.clean_text(text)
    match = re.match(r"^(.+?[.!?])(?:\s+|$)(.*)$", text, flags=re.S)
    if not match:
        return text, ""
    return match.group(1).strip(), match.group(2).strip()


def _repeats_title(title: str, sentence: str) -> bool:
    title_norm = re.sub(r"\W+", " ", title.casefold()).strip()
    sentence_norm = re.sub(r"\W+", " ", sentence.casefold()).strip()
    if title_norm and (title_norm in sentence_norm or sentence_norm in title_norm):
        return True

    title_tokens = _tokens(title)
    sentence_tokens = _tokens(sentence)
    if not title_tokens or not sentence_tokens:
        return False
    common = title_tokens & sentence_tokens
    similarity = len(common) / max(1, min(len(title_tokens), len(sentence_tokens)))
    return len(common) >= 3 and similarity >= 0.38


def telegram_text_no_repeated_intro(rendered: bot.Rendered, story: bot.Story) -> str:
    summary = bot.clean_text(rendered.telegram_summary_ru)
    first, rest = _first_sentence(summary)

    if rest and len(rest) >= 100 and _repeats_title(rendered.title_ru, first):
        bot.LOG.info("Removed Telegram intro that repeated headline: %s", first[:160])
        rendered = bot.Rendered(
            title_ru=rendered.title_ru,
            telegram_summary_ru=rest,
            threads_teaser_ru=rendered.threads_teaser_ru,
            event_key=rendered.event_key,
            quote_ru=rendered.quote_ru,
            quote_original=rendered.quote_original,
            speaker_ru=rendered.speaker_ru,
        )

    return _original_telegram_text(rendered, story)


bot.telegram_text = telegram_text_no_repeated_intro
