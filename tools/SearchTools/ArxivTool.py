import arxiv
import logging

def search_arxiv(query, max_results=3):
    """
    Fetches scientific and research papers from ArXiv using the latest Client-based API.
    """
    if not query: 
        return "Error: Empty ArXiv search query."
    
    try:
        client = arxiv.Client()
        
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        results_text = f"🔬 ARXIV RESEARCH PAPERS FOR '{query}':\n\n"
        papers_found = False
        
        for result in client.results(search):
            papers_found = True
            
            clean_summary = result.summary.replace('\n', ' ').strip()
            authors = ', '.join([a.name for a in result.authors])
            
            results_text += f"Title: {result.title}\n"
            results_text += f"Published: {result.published.strftime('%Y-%m-%d')} | Category: {result.primary_category}\n"
            results_text += f"Authors: {authors}\n"
            results_text += f"Paper Link: {result.entry_id}\n"
            results_text += f"PDF Link: {result.pdf_url}\n"
            results_text += f"Abstract: {clean_summary}\n"
            results_text += "-" * 60 + "\n\n"
            
        return results_text if papers_found else f"No relevant research papers found on ArXiv."
        
    except Exception as e:
        logging.error(f"ArXiv Error: {e}")
        return f"ArXiv search failed: {str(e)}"

if __name__ == "__main__":
    print(search_arxiv("quantum error correction 2024", max_results=2))