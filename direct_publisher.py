from __future__ import annotations

import os
import subprocess
import time

import bot
import publisher  # applies studio sources, dedupe and Gemini/source-language fallback
import gemini_priority  # try Gemini 3.5 Flash Lite on every key before 3.1 Flash Lite
import telegram_cleanup  # remove body intro when it repeats the Telegram headline
import media_cleanup  # reject JPG/PNG/etc. mistakenly detected as gameplay video
import direct_feeds  # wraps the active collector with direct first-party/outlet RSS feeds
import block_pcgamer  # remove PC Gamer from RSS, Bing and any accidental cross-source URLs
import block_stopgame  # remove StopGame from RSS, Bing and any accidental cross-source URLs
import gaming_relevance  # block movies/TV/streaming stories without a clear gaming connection
import disable_threads  # hard-disable Threads publishing; Telegram-only mode
import telegram_format  # preserve blank lines in Telegram captions at final send stage


# bot.main() writes data/posted.json immediately after Telegram accepts a post, but
# GitHub Actions used to push that file only in the final workflow step. A queued
# run could therefore start from an older event commit, or a transient git push
# failure could lose the publication record and allow the exact URL to be posted
# again. Persist each real publication to main immediately; the workflow-level
# state merge remains as a backup.
_original_save_state = bot.save_state


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        text=True,
        capture_output=True,
        timeout=45,
    )


def _checkpoint_publication_history() -> None:
    if bot.DRY_RUN or os.getenv("GITHUB_ACTIONS", "").lower() != "true":
        return

    state_path = str(bot.STATE_PATH)
    committed = False
    try:
        _git("config", "user.name", "github-actions[bot]")
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git("add", state_path)

        # Nothing new to persist (for example a second save in the same run).
        if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return

        _git("commit", "-m", "Checkpoint gaming publication history")
        committed = True

        last_error = ""
        for attempt in range(1, 5):
            result = _git("push", "origin", "HEAD:main", check=False)
            if result.returncode == 0:
                bot.LOG.info("Publication history checkpoint pushed to main")
                return
            last_error = (result.stderr or result.stdout or "git push failed").strip()
            bot.LOG.warning(
                "Publication history checkpoint push failed (%d/4): %s",
                attempt,
                last_error[-500:],
            )
            time.sleep(attempt * 2)

        # Restore the state as an uncommitted change so the workflow's final
        # merge/push step can still persist it instead of seeing a clean tree.
        if committed:
            _git("reset", "--mixed", "HEAD~1", check=False)
        bot.LOG.error("Immediate publication checkpoint failed after retries; final workflow save will retry")
    except (subprocess.SubprocessError, OSError) as exc:
        if committed:
            _git("reset", "--mixed", "HEAD~1", check=False)
        bot.LOG.error("Immediate publication checkpoint failed: %s", exc)


def save_state_with_checkpoint(state: dict) -> None:
    _original_save_state(state)
    _checkpoint_publication_history()


bot.save_state = save_state_with_checkpoint


if __name__ == "__main__":
    raise SystemExit(bot.main())
