from __future__ import annotations

import os

import bot
import publisher


# Only these two Gemini models are allowed anywhere in the runtime.
_MODEL_ORDER = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
_ALLOWED_MODELS = set(_MODEL_ORDER)


# bot.py still contains an old non-Lite default for GEMINI_MODEL. Guard the config
# at runtime so gemini-3.5-flash can never be called even if an environment variable
# is missing or misconfigured.
_original_gemini_config = bot.gemini_config


def gemini_config_lite_only() -> tuple[str, str, str]:
    key, model, fallback = _original_gemini_config()
    if model not in _ALLOWED_MODELS:
        bot.LOG.warning("Blocked disallowed Gemini model %s; forcing gemini-3.5-flash-lite", model)
        model = "gemini-3.5-flash-lite"
    if fallback not in _ALLOWED_MODELS:
        bot.LOG.warning("Blocked disallowed Gemini fallback %s; forcing gemini-3.1-flash-lite", fallback)
        fallback = "gemini-3.1-flash-lite"
    return key, model, fallback


bot.gemini_config = gemini_config_lite_only


def rewrite_story_gemini_priority(story: bot.Story) -> tuple[bot.Rendered, str]:
    keys = publisher._configured_gemini_keys()
    if not keys:
        bot.LOG.warning("No Gemini API keys configured")
        return publisher._fallback_render(story)

    previous_key = os.environ.get("GEMINI_API_KEY")
    previous_model = os.environ.get("GEMINI_MODEL")
    previous_fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL")

    try:
        # Exhaust every configured project with Gemini 3.5 Flash Lite first.
        # Gemini 3.1 Flash Lite is only used if 3.5 Flash Lite fails on every key.
        for model_index, model in enumerate(_MODEL_ORDER, start=1):
            os.environ["GEMINI_MODEL"] = model
            # bot.rewrite_story internally tries primary/fallback. Set both to the
            # same model so it cannot jump to 3.1 before all 3.5 Lite keys are exhausted.
            os.environ["GEMINI_FALLBACK_MODEL"] = model
            if model_index == 2:
                bot.LOG.warning(
                    "All Gemini 3.5 Flash Lite projects unavailable; switching to Gemini 3.1 Flash Lite"
                )

            for key_index, (name, key) in enumerate(keys, start=1):
                os.environ["GEMINI_API_KEY"] = key
                bot.LOG.info(
                    "Trying %s with Gemini key %d/%d (%s)",
                    model,
                    key_index,
                    len(keys),
                    name,
                )
                try:
                    result = publisher._original_rewrite_story(story)
                    bot.LOG.info(
                        "Gemini succeeded: model=%s key=%d/%d (%s)",
                        model,
                        key_index,
                        len(keys),
                        name,
                    )
                    return result
                except RuntimeError as exc:
                    if not publisher._is_gemini_error(exc):
                        raise
                    bot.LOG.warning(
                        "Gemini unavailable: model=%s key=%d/%d (%s): %s",
                        model,
                        key_index,
                        len(keys),
                        name,
                        str(exc).splitlines()[0],
                    )
                    continue
    finally:
        if previous_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = previous_key
        if previous_model is None:
            os.environ.pop("GEMINI_MODEL", None)
        else:
            os.environ["GEMINI_MODEL"] = previous_model
        if previous_fallback_model is None:
            os.environ.pop("GEMINI_FALLBACK_MODEL", None)
        else:
            os.environ["GEMINI_FALLBACK_MODEL"] = previous_fallback_model

    return publisher._fallback_render(story)


bot.rewrite_story = rewrite_story_gemini_priority
