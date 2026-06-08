from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .WebSearch import search_web
from .ArxivTool import search_arxiv
from .YoutubeTranscriptFetcher import fetch_youtube_transcript  
from .Scraper import scrape_webpage

def execute_search_actions(search_actions_dict):
    """
    Processes search actions dictionary.
    Routes to Web, ArXiv, YouTube, and Webpage Reader (Jina).
    """
    if not search_actions_dict or not isinstance(search_actions_dict, dict):
        return ""

    combined_results = ""
    futures = {}
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        
        if search_actions_dict.get("web"):
            futures[executor.submit(search_web, search_actions_dict["web"])] = "Web"
            
        if search_actions_dict.get("arxiv"):
            futures[executor.submit(search_arxiv, search_actions_dict["arxiv"])] = "ArXiv"
            
        if search_actions_dict.get("youtube"):
            futures[executor.submit(fetch_youtube_transcript, search_actions_dict["youtube"])] = "YouTube"
            
        if search_actions_dict.get("read_webpage"):
            futures[executor.submit(scrape_webpage, search_actions_dict["read_webpage"])] = "Web Reader"
            
        for future in as_completed(futures):
            source = futures[future]
            try:
                result_text = future.result()
                if result_text:
                    combined_results += f"--- {source} Results ---\n{result_text}\n"
            except Exception as e:
                logging.error(f"Error in {source} thread: {e}")
                
    return combined_results