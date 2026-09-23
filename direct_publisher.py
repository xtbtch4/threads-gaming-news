from __future__ import annotations

import bot
import publisher  # applies studio sources, dedupe and Gemini/source-language fallback
import direct_feeds  # wraps the active collector with direct first-party/outlet RSS feeds
import disable_threads  # hard-disable Threads publishing; Telegram-only mode


if __name__ == "__main__":
    raise SystemExit(bot.main())
