from __future__ import annotations

import bot
import publisher  # applies studio sources, dedupe and Gemini/source-language fallback
import gemini_priority  # try Gemini 3.5 Flash Lite on every key before 3.1 Flash Lite
import telegram_cleanup  # remove body intro when it repeats the Telegram headline
import media_cleanup  # reject JPG/PNG/etc. mistakenly detected as gameplay video
import direct_feeds  # wraps the active collector with direct first-party/outlet RSS feeds
import block_pcgamer  # remove PC Gamer from RSS, Bing and any accidental cross-source URLs
import disable_threads  # hard-disable Threads publishing; Telegram-only mode
import telegram_format  # preserve blank lines in Telegram captions at final send stage


if __name__ == "__main__":
    raise SystemExit(bot.main())
