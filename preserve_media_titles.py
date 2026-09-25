from __future__ import annotations

import requests


# Inject a strict naming rule into every Gemini rewrite request without duplicating
# bot.rewrite_story. All titles of games, films, series, DLCs and franchises must stay
# exactly as written in the source language; only surrounding prose is translated.
_original_post = requests.post


_TITLE_RULE = (
    " ВАЖНО: названия видеоигр, фильмов, сериалов, дополнений/DLC и франшиз НЕ переводи "
    "и НЕ транслитерируй. Сохраняй их ровно в оригинальном написании из источника, "
    "включая латиницу, цифры, двоеточия и подзаголовки. Например: Avengers: Endgame, "
    "Control Resonant, Call of Duty: Warzone. Это правило действует в title_ru, "
    "telegram_summary_ru, threads_teaser_ru и speaker/quote-контексте. Переводи только "
    "остальной обычный текст. Если не уверен, является ли фраза названием произведения, "
    "оставь её в исходном виде."
)


def post_with_preserved_titles(url, *args, **kwargs):
    if "generativelanguage.googleapis.com" in str(url):
        payload = kwargs.get("json")
        if isinstance(payload, dict) and "system_instruction" in payload:
            payload = dict(payload)
            instruction = str(payload.get("system_instruction") or "")
            if _TITLE_RULE not in instruction:
                payload["system_instruction"] = instruction + _TITLE_RULE
            kwargs["json"] = payload
    return _original_post(url, *args, **kwargs)


requests.post = post_with_preserved_titles
