from __future__ import annotations

import re

import bot


def shorten_preserve_paragraphs(text: str, limit: int) -> str:
    """Shorten Telegram text without collapsing paragraph breaks."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]

    chunk = text[: limit - 1].rstrip()
    cut = max(chunk.rfind("\n"), chunk.rfind(" "))
    if cut >= max(40, (limit - 1) // 2):
        chunk = chunk[:cut].rstrip()
    return chunk.rstrip(" ,;:-.") + "…"


# bot.publish_telegram calls bot.shorten() for sendPhoto captions. The original
# shorten() runs clean_text(), which collapses all newlines into spaces. Replacing
# only this helper keeps the title/summary paragraph break intact at send time.
bot.shorten = shorten_preserve_paragraphs
