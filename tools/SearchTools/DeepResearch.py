import os
import json
import logging
import time
import re
import glob
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tavily import TavilyClient

from core.brain.config import GEMINI_AGENT_MODEL, DEEP_RESEARCH_TIMEOUT, GEMINI_API_KEY
from core.ui.agent_status import update_agent_status
from core.logger.logger import logger

load_dotenv()

CREATIONS_DIR = Path.home() / "Documents" / "Jarvis" / "DeepResearch"
CREATIONS_DIR.mkdir(parents=True, exist_ok=True)

def generate_filename_from_ai(topic, report_content, client, model_name):
    prompt = f"""
Topic: {topic}

Report content (first 2000 chars):
{report_content[:2000]}

Task: Generate a SHORT, descriptive filename for this research report.
Rules:
- Only lowercase letters, numbers, underscores (_)
- No spaces, no special characters except underscore
- Max length: 50 characters
- Must end with .md
- Example: "solid_state_batteries_analysis.md" or "financial_crisis_2008.md"

Return ONLY the filename, nothing else.
"""
    try:
        config = types.GenerateContentConfig(temperature=0.2)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        filename = response.text.strip().split("\n")[0].strip()
        filename = re.sub(r'[^a-z0-9_.]', '_', filename.lower())
        if not filename.endswith('.md'):
            filename += '.md'
        if len(filename) > 60:
            filename = filename[:55] + '.md'
        return filename
    except Exception as e:
        logger.error(f"AI filename generation failed: {e}")
        return None

def deep_research(topic, max_steps=None):
    logger.info(f"TAVILY DEEP RESEARCH START: {topic}")

    try:
        update_agent_status(
            step=1, total_steps=5,
            thought=f"Initiating advanced Tavily Pro research for '{topic}'...",
            action="deep_research", action_detail="STARTING TASK"
        )
    except Exception:
        pass

    try:
        tavily_api_key = os.getenv('TAVILY_API_KEY')
        if not tavily_api_key:
            logger.error("TAVILY_API_KEY missing in .env")
            return "Error: TAVILY_API_KEY missing in .env"

        tavily_client = TavilyClient(api_key=tavily_api_key)

        logger.info("Requesting Tavily Pro Research (this may take a few minutes)...")
        response = tavily_client.research(topic, model="pro")
        request_id = response.get("request_id")

        if not request_id:
            logger.error(f"Task creation failed. Response: {response}")
            return f"Error: Could not start research task. Response: {response}"

        logger.info(f"Research Task created. Request ID: {request_id}")

        start_time = time.time()
        timeout = DEEP_RESEARCH_TIMEOUT if DEEP_RESEARCH_TIMEOUT else 600
        poll_interval = 10

        result_content = ""
        sources = []

        while True:
            elapsed_time = int(time.time() - start_time)
            if elapsed_time > timeout:
                logger.warning("Timeout reached while polling Tavily")
                return "Error: Research task timed out."

            time.sleep(poll_interval)

            try:
                update_agent_status(
                    step=2, total_steps=5,
                    thought=f"Tavily is synthesizing data... (Elapsed: {elapsed_time}s)",
                    action="deep_research", action_detail="POLLING"
                )
            except Exception:
                pass

            status_res = tavily_client.get_research(request_id)
            status = status_res.get("status")
            logger.info(f"Status: {status.upper()} (Elapsed: {elapsed_time}s)")

            if status == "completed":
                result_content = status_res.get("content", "No content returned.")
                sources = status_res.get("sources", [])
                break
            elif status == "failed":
                logger.error("Tavily research task failed.")
                return "Error: Tavily research task failed."

        final_report = result_content
        if sources:
            final_report += "\n\n### References / Sources\n"
            for i, src in enumerate(sources, 1):
                title = src.get("title", "No Title")
                url = src.get("url", "No URL")
                final_report += f"{i}. [{title}]({url})\n"

        try:
            update_agent_status(
                step=4, total_steps=5,
                thought="Research complete. Naming and formatting report...",
                action="deep_research", action_detail="FINALIZING"
            )
        except Exception:
            pass

        client = genai.Client(api_key=GEMINI_API_KEY)
        ai_filename = generate_filename_from_ai(topic, final_report, client, GEMINI_AGENT_MODEL)

        if not ai_filename:
            safe_topic = re.sub(r'[^a-zA-Z0-9]', '_', topic.lower())[:40]
            timestamp = int(time.time())
            ai_filename = f"report_{safe_topic}_{timestamp}.md"

        filepath = CREATIONS_DIR / ai_filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_report)

        try:
            update_agent_status(
                step=5, total_steps=5,
                thought="Report saved successfully.",
                action="deep_research", action_detail="COMPLETED"
            )
        except Exception as e:
            pass

        logger.info(f"Report saved to {filepath}")
        logger.info(f"Report automatically saved as: {ai_filename}")
        logger.info(f"Location: {CREATIONS_DIR.resolve()}")

        return final_report

    except Exception as e:
        logger.error(f"Tavily Deep Research failed: {e}")
        return f"Error: {str(e)}"

def deep_research_as_tool(topic: str) -> str:
    try:
        report = deep_research(topic)
        if report.startswith("Error"):
            return report

        pattern = os.path.join(str(CREATIONS_DIR), "*.md")
        files = glob.glob(pattern)
        latest_file = max(files, key=os.path.getctime) if files else None

        if latest_file:
            filename = os.path.basename(latest_file)
            return f"Deep research completed successfully. Report saved as '{filename}' at absolute path: {os.path.abspath(latest_file)}. Report length: {len(report)} characters."
        else:
            return f"Deep research completed but file not found? Report content preview: {report[:300]}..."
    except Exception as e:
        return f"Deep research failed: {str(e)}"

if __name__ == "__main__":
    query = input("🤖 Enter research topic: ")
    deep_research(query)