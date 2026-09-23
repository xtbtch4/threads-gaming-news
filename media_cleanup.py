from __future__ import annotations

from urllib.parse import urlsplit

import bot
import run_bot


_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
_VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v")


def _path_extension(url: str) -> str:
    return urlsplit(url or "").path.casefold()


def _is_obvious_image(url: str) -> bool:
    path = _path_extension(url)
    return any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _looks_like_real_video(url: str) -> bool:
    if not url or _is_obvious_image(url):
        return False

    low = url.casefold()
    path = _path_extension(url)
    if any(path.endswith(ext) for ext in _VIDEO_EXTENSIONS):
        return True
    if any(host in low for host in ("youtube.com", "youtu.be", "vimeo.com", "twitch.tv")):
        return True

    # Resolved CDN video URLs often have no extension. Ask the server only when
    # the URL itself is ambiguous. Never reject an otherwise valid URL merely
    # because HEAD is unsupported; only reject a confirmed image content type.
    try:
        response = bot.requests.head(
            url,
            allow_redirects=True,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GamingNewsBot/1.0)"},
        )
        content_type = response.headers.get("content-type", "").casefold()
        if content_type.startswith("image/"):
            return False
        if content_type.startswith("video/"):
            return True
    except bot.requests.RequestException:
        pass

    # Unknown extensionless URLs were already selected by yt-dlp or video metadata;
    # keep them unless they are positively identified as an image.
    return True


_original_discover_gameplay_video = run_bot.discover_gameplay_video


def discover_gameplay_video_media_safe(story: bot.Story) -> str:
    url = _original_discover_gameplay_video(story)
    if url and not _looks_like_real_video(url):
        bot.LOG.warning("Rejected non-video media from gameplay detector: %s", url)
        return ""
    return url


run_bot.discover_gameplay_video = discover_gameplay_video_media_safe


_original_publish_telegram = bot.publish_telegram


def publish_telegram_media_safe(rendered: bot.Rendered, story: bot.Story, image_url: str):
    video_url = run_bot.VIDEO_BY_STORY.get(story.url, "")
    if video_url and not _looks_like_real_video(video_url):
        bot.LOG.warning("Telegram media guard rejected image masquerading as video: %s", video_url)
        run_bot.VIDEO_BY_STORY[story.url] = ""
        if run_bot.CURRENT_STORY_URL == story.url:
            run_bot.CURRENT_VIDEO_URL = ""
    return _original_publish_telegram(rendered, story, image_url)


bot.publish_telegram = publish_telegram_media_safe
