from __future__ import annotations

import html
import os
import re

import bot
import publisher


MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_original_fallback_render = publisher._fallback_render


def _looks_russian(text: str) -> bool:
    text = bot.clean_text(text)
    if not text:
        return False
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return cyr >= 8 and cyr >= latin


def _split_chunks(text: str, limit: int = 430) -> list[str]:
    text = bot.clean_text(text)
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > limit:
            words = sentence.split()
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if piece and len(candidate) > limit:
                    chunks.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                if current and len(current) + 1 + len(piece) <= limit:
                    current = f"{current} {piece}"
                else:
                    if current:
                        chunks.append(current)
                    current = piece
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def _translate_chunk(text: str) -> str:
    params = {"q": text, "langpair": "en|ru", "mt": "1"}
    email = os.getenv("MYMEMORY_EMAIL", "").strip()
    if email:
        params["de"] = email

    response = bot.requests.get(MYMEMORY_URL, params=params, timeout=18)
    response.raise_for_status()
    data = response.json()
    status = str(data.get("responseStatus", "200"))
    if status and status != "200":
        raise RuntimeError(f"MyMemory responseStatus={status}")

    translated = html.unescape(str(data.get("responseData", {}).get("translatedText") or "")).strip()
    translated = bot.clean_text(translated)
    if not translated:
        raise RuntimeError("MyMemory returned empty translation")
    return translated


def _translate_text(text: str) -> str:
    text = bot.clean_text(text)
    if not text or _looks_russian(text):
        return text
    if not re.search(r"[A-Za-z]", text):
        raise RuntimeError("MyMemory fallback only translates English/Latin source text")

    translated = [_translate_chunk(chunk) for chunk in _split_chunks(text)]
    result = bot.clean_text(" ".join(translated))
    if not result:
        raise RuntimeError("MyMemory produced no translated text")
    return result


def mymemory_fallback_render(story: bot.Story) -> tuple[bot.Rendered, str]:
    """Translate to Russian with MyMemory after all Gemini attempts fail."""
    evidence, image_url, _quotes = bot.fetch_article_context(story)
    source_title = bot.clean_text(story.title)
    source_base = bot.clean_text(story.summary) or bot.clean_text(evidence) or source_title
    source_summary = publisher._sentence_excerpt(source_base, 680)

    try:
        title_ru = _translate_text(source_title)
        summary_ru = _translate_text(source_summary)
        teaser_ru = publisher._sentence_excerpt(summary_ru, 280)

        words = re.findall(r"[a-z0-9]{3,}", source_title.casefold())[:10]
        event_key = " ".join(words) if words else f"fallback {story.fingerprint}"
        rendered = bot.Rendered(
            title_ru=title_ru,
            telegram_summary_ru=summary_ru,
            threads_teaser_ru=teaser_ru,
            event_key=event_key,
        )
        bot.LOG.warning("Gemini unavailable; MyMemory Russian fallback succeeded: %s", source_title)
        return rendered, image_url
    except Exception as exc:
        bot.LOG.warning("MyMemory fallback unavailable; using source language: %s", str(exc).splitlines()[0])
        return _original_fallback_render(story)


# rewrite_story_resilient in publisher resolves this global fallback at call time.
publisher._fallback_render = mymemory_fallback_render
