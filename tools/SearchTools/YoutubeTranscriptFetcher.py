from youtube_transcript_api import YouTubeTranscriptApi
import re

def fetch_youtube_transcript(video_url):
    """
    YouTube video se transcript fetch karta hai aur formatted string return karta hai.
    Agar error aata hai to error message return hota hai.
    """
    try:
        video_id = re.search(r"(?<=v=)[^&#]+", video_url).group()
        
        ytt_api = YouTubeTranscriptApi()
        
        common_languages = ['hi', 'en', 'en-IN', 'ur', 'pa', 'mr', 'gu']
        fetched_transcript = ytt_api.fetch(video_id, languages=common_languages) 
        
        full_text = " ".join([snippet.text for snippet in fetched_transcript])
        
        return f"--- YouTube Transcript ---\n{full_text}"
        
    except Exception as e:
        error_msg = f"Could not fetch transcript: {e}"
        return error_msg

if __name__ == "__main__":
    result = fetch_youtube_transcript("https://www.youtube.com/watch?v=Zmz5gE9nJqY")
    print(result)