from __future__ import annotations

import bot
import publisher  # applies studio sources, dedupe and Gemini/media fallbacks
import direct_feeds  # wraps the active collector with direct first-party/outlet RSS feeds


if __name__ == "__main__":
    raise SystemExit(bot.main())
