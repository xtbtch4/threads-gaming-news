from __future__ import annotations

import re

import bot


_original_telegram_text = bot.telegram_text

_STOP = {
    "после", "перед", "через", "среди", "также", "когда", "который", "которая", "которые",
    "компания", "компании", "студия", "студии", "система", "системы", "новый", "новая", "новые",
    "with", "after", "before", "from", "that", "this", "their", "company", "studio", "system", "new",
}

# Canonical concepts let us catch paraphrases such as
# "возрастная верификация" ~ "возрастная проверка" and
# "добавила поддержку" ~ "начала внедрение".
_CANON_PREFIXES = {
    "верифик": "verify",
    "провер": "verify",
    "verification": "verify",
    "verify": "verify",
    "поддерж": "support",
    "внедр": "support",
    "добав": "support",
    "support": "support",
    "implement": "support",
    "запуст": "launch",
    "запуск": "launch",
    "возобнов": "launch",
    "launch": "launch",
    "release": "launch",
}


def _stem(token: str) -> str:
    token = token.casefold().replace("ё", "е")
    for suffix in (
        "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ией", "иях",
        "ость", "ости", "ение", "ения", "ений", "ировать", "ирует", "ировали",
        "ов", "ев", "ей", "ой", "ий", "ый", "ая", "ое", "ые", "ую", "юю",
        "ам", "ям", "ах", "ях", "ом", "ем", "а", "я", "ы", "и", "у", "ю", "е",
        "ing", "ed", "es", "s",
    ):
        if len(token) >= 7 and token.endswith(suffix):
            token = token[:-len(suffix)]
            break
    return token


def _canonical(token: str) -> str:
    stem = _stem(token)
    for prefix, canonical in _CANON_PREFIXES.items():
        if stem.startswith(prefix):
            return canonical
    return stem


def _tokens(text: str) -> set[str]:
    result: set[str] = set()
    # Keep 3-character names such as AMD, EA, PS5-like product tokens, etc.
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9+.-]{2,}", text or ""):
        token = _canonical(raw.strip("+.-"))
        if token and token not in _STOP and len(token) >= 3:
            result.add(token)
    return result


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9+.-]{2,}", text or ""):
        clean = raw.strip("+.-")
        low = clean.casefold()
        # Product/technology codes and acronyms are strong semantic anchors.
        if any(ch.isdigit() for ch in clean) or (clean.isupper() and len(clean) >= 3):
            anchors.add(_canonical(clean))
            continue
        # Latin product/company names such as Discord, Nvidia, PlayStation are also useful anchors.
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]{4,}", clean) and low not in _STOP:
            anchors.add(_canonical(clean))
    return anchors


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
    if len(common) >= 3 and similarity >= 0.34:
        return True

    common_anchors = _anchors(title) & _anchors(sentence)
    # Example: AMD + GDDR7 appears in both headline and intro even when the verbs are paraphrased.
    if len(common_anchors) >= 2 and len(common) >= 2:
        return True
    # One strong named anchor plus two matching concepts is also enough for a short intro.
    if common_anchors and len(common) >= 3 and len(sentence) <= 240:
        return True
    return False


def _separate_headline(text: str, title: str) -> str:
    """Keep the Telegram headline as its own paragraph without a divider line."""
    text = text.strip()
    title_line = f"🎮 {bot.clean_text(title).rstrip(' .…')}"
    if not text.startswith(title_line):
        return text
    rest = text[len(title_line):].lstrip()
    if not rest:
        return text
    return f"{title_line}\n\n{rest}"


def telegram_text_no_repeated_intro(rendered: bot.Rendered, story: bot.Story) -> str:
    summary = bot.clean_text(rendered.telegram_summary_ru)
    first, rest = _first_sentence(summary)

    if rest and len(rest) >= 100 and _repeats_title(rendered.title_ru, first):
        bot.LOG.info("Removed Telegram intro that repeated headline semantically: %s", first[:180])
        rendered = bot.Rendered(
            title_ru=rendered.title_ru,
            telegram_summary_ru=rest,
            threads_teaser_ru=rendered.threads_teaser_ru,
            event_key=rendered.event_key,
            quote_ru=rendered.quote_ru,
            quote_original=rendered.quote_original,
            speaker_ru=rendered.speaker_ru,
        )

    text = _original_telegram_text(rendered, story)
    return _separate_headline(text, rendered.title_ru)


bot.telegram_text = telegram_text_no_repeated_intro
