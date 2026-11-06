from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .WebSearch import search_web
from .ArxivTool import search_arxiv
from .YoutubeTranscriptFetcher import fetch_youtube_transcript
from .Scraper import scrape_webpage


def _is_tool_error(text):
    if not text:
        return True
    stripped = str(text).strip()
    if not stripped:
        return True
    if stripped.startswith("Observation: Error"):
        return True
    if stripped.lower().startswith("<error>"):
        return True
    return False


def execute_search_actions(search_actions_dict):
    if not search_actions_dict or not isinstance(search_actions_dict, dict):
        return "Observation: Error -> No search parameters provided."

    combined_results = ""
    futures = {}
    success_count = 0
    failure_count = 0
    failure_details = []

    with ThreadPoolExecutor(max_workers=4) as executor:

        if search_actions_dict.get("web"):
            futures[executor.submit(search_web, search_actions_dict["web"])] = "Web"

        if search_actions_dict.get("arxiv"):
            futures[executor.submit(search_arxiv, search_actions_dict["arxiv"])] = "ArXiv"

        if search_actions_dict.get("youtube"):
            futures[executor.submit(fetch_youtube_transcript, search_actions_dict["youtube"])] = "YouTube"

        if search_actions_dict.get("read_webpage"):
            futures[executor.submit(scrape_webpage, search_actions_dict["read_webpage"])] = "Web Reader"

        if not futures:
            return "Observation: Error -> No valid search parameters provided."

        for future in as_completed(futures):
            source = futures[future]
            try:
                result_text = future.result()
                if _is_tool_error(result_text):
                    failure_count += 1
                    failure_details.append(f"{source}: {str(result_text)[:140]}")
                else:
                    success_count += 1
                    combined_results += f"--- {source} Results ---\n{result_text}\n"
            except Exception as e:
                logging.error(f"Error in {source} thread: {e}")
                failure_count += 1
                failure_details.append(f"{source}: exception {str(e)[:100]}")

    if success_count == 0:
        return (
            "Observation: Error -> All search sources failed. "
            + " | ".join(failure_details)
            + ". Do NOT retry."
        )

    if failure_count > 0:
        combined_results += f"\n[Note: {failure_count} source(s) failed: {' | '.join(failure_details)}]\n"

    return combined_results