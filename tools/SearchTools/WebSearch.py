import os
import logging
from tavily import TavilyClient
from dotenv import load_dotenv

logging.basicConfig(
    filename='Data/tavily_search.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

def search_web(query, max_results=5):
    """Pro-Level Web Search using Tavily (XML Format for AI Agents)"""
    try:
        if not query: 
            return "<error>Empty search query.</error>"

        api_key = os.getenv('TAVILY_API_KEY')
        if not api_key:
            logging.error("TAVILY_API_KEY not set in .env")
            return "<error>TAVILY_API_KEY missing.</error>"

        client = TavilyClient(api_key=api_key)
        
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,        
            include_raw_content=True     
        )
        
        results = response.get("results", [])
        if not results:
            return f'<web_search_results query="{query}"><message>No web results found.</message></web_search_results>'

        xml_output = f'<web_search_results query="{query}">\n'
        xml_output += '  <detailed_sources>\n'

        for i, r in enumerate(results, 1):
            title = r.get('title', 'N/A')
            url = r.get('url', 'N/A')
            
            raw_content = r.get('raw_content', '')
            snippet = r.get('content', '')
            
            content_to_use = raw_content if raw_content else snippet
            
            clean_content = content_to_use.strip()[:20000]
            
            xml_output += f'    <source id="{i}">\n'
            xml_output += f'      <title>{title}</title>\n'
            xml_output += f'      <url>{url}</url>\n'
            xml_output += f'      <content>\n{clean_content}\n      </content>\n'
            xml_output += f'    </source>\n'

        xml_output += '  </detailed_sources>\n'
        xml_output += '</web_search_results>'

        return xml_output

    except Exception as e:
        logging.error(f"Error in Tavily search_web: {e}")
        return f"<error>Web search failed: {e}</error>"
    
def quick_snippet_search(query: str, max_results: int = 2) -> str:
    try:
        if not query:
            return "No query provided."

        api_key = os.getenv('TAVILY_API_KEY')
        if not api_key:
            return "Search API key missing."

        client = TavilyClient(api_key=api_key)
        
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,         
            include_raw_content=False    
        )
        
        direct_answer = response.get("answer", "")
        results = response.get("results", [])
        
        if not results and not direct_answer:
            return "No real-time facts found."

        output_lines = []
        if direct_answer:
            output_lines.append(f"Direct Answer: {direct_answer}")
            
        for i, r in enumerate(results[:max_results], 1):
            title = r.get('title', 'N/A')
            snippet = r.get('content', '').strip().replace('\n', ' ')
            output_lines.append(f"[{i}] {title}: {snippet}")

        return "\n".join(output_lines)

    except Exception as e:
        logging.error(f"Quick search error: {e}")
        return "Real-time search unavailable right now."