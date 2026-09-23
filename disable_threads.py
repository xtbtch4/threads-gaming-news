from __future__ import annotations

import bot


def publish_threads_disabled(teaser: str, telegram_url: str, image_url: str = "") -> str:
    """Hard-disable all Threads API publishing while keeping Telegram flow intact."""
    bot.LOG.info("Threads publication disabled; Telegram-only mode")
    return "disabled"


def retry_pending_threads_disabled(state: dict) -> None:
    """Do not retry older Telegram posts to Threads."""
    return None


bot.publish_threads = publish_threads_disabled
bot.retry_pending_threads = retry_pending_threads_disabled
