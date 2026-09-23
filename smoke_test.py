from __future__ import annotations

import logging

import bot


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = bot.load_state()
    stories = bot.fetch_stories()
    logging.info("Smoke test: found %d fresh stories", len(stories))
    selected = bot.select_stories(stories, state)
    if not selected:
        logging.info("Smoke test passed: collector works, but no story met the current threshold")
        return 0

    story = selected[0]
    evidence, image_url, quotes = bot.fetch_article_context(story)
    logging.info("Smoke test candidate: [%s] score=%s %s", story.source, story.score, story.title)
    logging.info("Article context: %d chars; quotes=%d; image=%s", len(evidence), len(quotes), image_url or "none")
    logging.info("Smoke test passed: no Telegram, Threads, or Gemini API call was made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
