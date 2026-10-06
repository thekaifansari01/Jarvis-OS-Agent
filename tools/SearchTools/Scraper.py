import os
import logging
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
logger = logging.getLogger(__name__)

def scrape_webpage(url: str) -> str:
    """
    Advanced Webpage Scraper using Tavily's Extract API.
    Handles dynamic content (JavaScript), bypasses basic bot protections, 
    and returns ultra-clean Markdown optimized for LLMs.
    """
    logger.info(f"🌐 Fetching webpage via Tavily Extract API: {url}")
    
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        logger.warning("⚠️ TAVILY_API_KEY not found in .env.")
        return "Observation: Error -> TAVILY_API_KEY missing in environment variables."
        
    try:
        client = TavilyClient(api_key=tavily_api_key)
        
        response = client.extract(urls=[url])
        
        failed_results = response.get("failed_results", [])
        if failed_results and any(f.get("url") == url for f in failed_results):
            error_msg = next((f.get("error") for f in failed_results if f.get("url") == url), "Unknown error")
            return f"Observation: Error -> Tavily couldn't extract content from this URL. Reason: {error_msg}. Website might have strict anti-bot security."
            
        results = response.get("results", [])
        if not results:
            return "Observation: Webpage load ho gayi par koi valid text/content nahi mila."
            
        data = results[0]
        clean_markdown = data.get("raw_content", "")
        
        if not clean_markdown:
            return f"Observation: URL se connect ho gaya par content empty return hua."
        
        if len(clean_markdown) > 15000:
            logger.warning("✂️ Content truncated to fit LLM Context Window.")
            clean_markdown = clean_markdown[:15000] + "\n\n... [🔴 Content Truncated due to length]"
            
        return f"Observation: Successfully fetched webpage content.\n\n📄 **Target URL**: {url}\n\n**Content**:\n{clean_markdown}\n\n💡 Hint: Now analyze or summarize this text to answer the user's query."
        
    except Exception as e:
        logger.error(f"Webpage reading tool error: {e}")
        return f"Observation: Webpage reading tool error -> {e}"

if __name__ == "__main__":
    test_url = input("🤖 Enter URL to scrape: ")
    print("Fetching...")
    print(scrape_webpage(test_url))