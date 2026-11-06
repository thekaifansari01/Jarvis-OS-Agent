from youtube_transcript_api import YouTubeTranscriptApi
import re
from core.logger.logger import logger

VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([a-zA-Z0-9_-]{11})",
    r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/v/)([a-zA-Z0-9_-]{11})",
    r"(?:^)([a-zA-Z0-9_-]{11})$",
]

PREFERRED_LANGUAGES = ['hi', 'en', 'en-IN', 'en-US', 'en-GB', 'ur', 'pa', 'mr', 'gu', 'bn', 'ta', 'te']


def _extract_video_id(video_url: str):
    if not video_url or not isinstance(video_url, str):
        return None
    url = video_url.strip()
    for pattern in VIDEO_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_youtube_transcript(video_url):
    logger.info(f"📺 Fetching YouTube transcript for: {video_url}")

    try:
        video_id = _extract_video_id(video_url)
        if not video_id:
            return f"Observation: Error -> Invalid YouTube URL. Could not extract video ID from '{video_url}'. Provide a valid full YouTube URL."

        logger.debug(f"Video ID: {video_id}")
        ytt_api = YouTubeTranscriptApi()

        fetched_transcript = None
        try:
            fetched_transcript = ytt_api.fetch(video_id, languages=PREFERRED_LANGUAGES)
        except Exception as lang_err:
            logger.warning(f"⚠️ Preferred language fetch failed ({lang_err}), trying auto-generated/any available...")
            try:
                transcript_list = ytt_api.list(video_id)
                for transcript in transcript_list:
                    try:
                        fetched_transcript = transcript.fetch()
                        logger.info(f"✅ Fallback transcript fetched (lang={transcript.language_code})")
                        break
                    except Exception:
                        continue
            except Exception as fallback_err:
                logger.error(f"❌ Fallback transcript listing failed: {fallback_err}")

        if not fetched_transcript:
            return f"Observation: Error -> YouTube transcript unavailable for video {video_id}. Reason: Captions may be disabled, video is age-restricted, or region-blocked. Do NOT retry with same URL."

        full_text = " ".join([snippet.text.strip() for snippet in fetched_transcript if snippet.text])
        full_text = re.sub(r"\s+", " ", full_text).strip()

        if not full_text:
            return f"Observation: Error -> YouTube transcript is empty for video {video_id}. Do NOT retry."

        logger.info(f"✅ YouTube transcript fetched, length: {len(full_text)} chars")
        return f"Observation: Success -> YouTube transcript fetched.\n--- YouTube Transcript ---\n{full_text}"

    except Exception as e:
        return f"Observation: Error -> YouTube transcript fetch failed: {str(e)}. Do NOT retry with same URL."


if __name__ == "__main__":
    result = fetch_youtube_transcript("https://www.youtube.com/watch?v=Zmz5gE9nJqY")
    print(result)