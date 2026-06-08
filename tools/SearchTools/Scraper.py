import os
import json
import requests
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

JINA_API_KEY = os.getenv("JINA_API_KEY")

def scrape_webpage(url: str) -> str:
    """
    Advanced Jina Reader API Integration.
    Fetches clean Markdown, uses API Key for VIP priority, and handles JSON parsing.
    """
    logger.info(f"🌐 Fetching webpage via Advanced Jina API: {url}")
    
    headers = {
        "Accept": "application/json",
        "X-Return-Format": "markdown"
    }
    
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"
        logger.info("🔑 Jina API Key injected for Priority Access.")
    else:
        logger.warning("⚠️ JINA_API_KEY not found in .env. Running in free limited mode.")
        
    jina_url = f"https://r.jina.ai/{url}"
    
    try:
        response = requests.get(jina_url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            page_title = data.get("data", {}).get("title", "No Title Found")
            clean_markdown = data.get("data", {}).get("content", "")
            
            if not clean_markdown:
                return f"Observation: Webpage load ho gayi par koi text nahi mila. Title tha: {page_title}"
            
            if len(clean_markdown) > 15000:
                logger.warning("✂️ Content truncated to fit LLM Context Window.")
                clean_markdown = clean_markdown[:15000] + "\n\n... [🔴 Content Truncated due to length]"
                
            return f"Observation: Successfully fetched webpage content.\n\n📄 **Title**: {page_title}\n\n**Content**:\n{clean_markdown}\n\n💡 Hint: Now analyze or summarize this text to answer the user's query."
            
        elif response.status_code == 429:
            return "Observation: Error [429] -> Rate limit hit. Traffic zyada hai."
            
        elif response.status_code == 403:
            return "Observation: Error [403] -> Is website par strict anti-bot security hai. Main isko nahi padh sakta."
            
        else:
            return f"Observation: Error -> Website padhne mein dikkat aayi (Status: {response.status_code})."
            
    except requests.exceptions.Timeout:
        return "Observation: Error -> Website ne respond karne mein bohot zyada time laga diya (Timeout)."
    except Exception as e:
        return f"Observation: Webpage reading tool error -> {e}"    