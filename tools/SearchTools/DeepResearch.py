import os
import time
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from tavily import TavilyClient

from core.ui.agent_status import update_agent_status
from core.logger.logger import logger


def _get_config_attr(*names, default=None):
    try:
        from core.brain import config as cfg
    except Exception:
        cfg = None
    if cfg is not None:
        for name in names:
            val = getattr(cfg, name, None)
            if val:
                return val
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return default


ROUTER_MODEL = _get_config_attr(
    "GEMINI_ROUTER_MODEL", "ROUTER_MODEL",
    "GEMINI_INTENT_MODEL", "INTENT_MODEL",
    "CLASSIFIER_MODEL", "FAST_MODEL",
)

AGENT_MODEL = _get_config_attr(
    "GEMINI_AGENT_MODEL", "AGENT_MODEL", "GEMINI_MODEL", "DEFAULT_MODEL",
    default="gemini-2.0-flash",
)

FILENAME_MODEL = ROUTER_MODEL or AGENT_MODEL or "gemini-2.0-flash-lite"

GEMINI_API_KEY = _get_config_attr("GEMINI_API_KEY", "GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
DEEP_RESEARCH_TIMEOUT = int(_get_config_attr("DEEP_RESEARCH_TIMEOUT", default=600))

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
        if not response or not response.text:
            logger.warning("AI filename generation returned empty response")
            return None
        filename = response.text.strip().split("\n")[0].strip()
        filename = re.sub(r'[^a-z0-9_.]', '_', filename.lower())
        if not filename.endswith('.md'):
            filename += '.md'
        if len(filename) > 60:
            filename = filename[:55] + '.md'
        return filename
    except Exception as e:
        logger.error(f"AI filename generation failed (model={model_name}): {e}")
        return None


def _fallback_filename(topic):
    safe_topic = re.sub(r'[^a-zA-Z0-9]', '_', topic.lower())[:40]
    return f"report_{safe_topic}_{int(time.time())}.md"


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
            return "Error: TAVILY_API_KEY missing in .env", None

        tavily_client = TavilyClient(api_key=tavily_api_key)

        logger.info("Requesting Tavily Pro Research (this may take a few minutes)...")
        response = tavily_client.research(topic, model="pro")
        request_id = response.get("request_id")

        if not request_id:
            logger.error(f"Task creation failed. Response: {response}")
            return f"Error: Could not start research task. Response: {response}", None

        logger.info(f"Research Task created. Request ID: {request_id}")

        start_time = time.time()
        timeout = DEEP_RESEARCH_TIMEOUT or 600
        poll_interval = 10

        result_content = ""
        sources = []

        while True:
            elapsed_time = int(time.time() - start_time)
            if elapsed_time > timeout:
                logger.warning("Timeout reached while polling Tavily")
                return "Error: Research task timed out.", None

            time.sleep(poll_interval)

            try:
                update_agent_status(
                    step=2, total_steps=5,
                    thought=f"Tavily is synthesizing data... (Elapsed: {elapsed_time}s)",
                    action="deep_research", action_detail="POLLING"
                )
            except Exception:
                pass

            try:
                status_res = tavily_client.get_research(request_id)
            except Exception as poll_err:
                logger.warning(f"Transient polling error (will retry): {poll_err}")
                continue

            status = status_res.get("status")
            logger.info(f"Status: {str(status).upper()} (Elapsed: {elapsed_time}s)")

            if status == "completed":
                result_content = status_res.get("content", "No content returned.")
                sources = status_res.get("sources", [])
                break
            elif status == "failed":
                logger.error("Tavily research task failed.")
                return "Error: Tavily research task failed.", None

        final_report = result_content
        if sources:
            final_report += "\n\n### References / Sources\n"
            for i, src in enumerate(sources, 1):
                if isinstance(src, dict):
                    title = src.get("title", "No Title")
                    url = src.get("url", "No URL")
                else:
                    title = str(src)
                    url = ""
                final_report += f"{i}. [{title}]({url})\n"

        try:
            update_agent_status(
                step=4, total_steps=5,
                thought="Research complete. Naming and formatting report...",
                action="deep_research", action_detail="FINALIZING"
            )
        except Exception:
            pass

        ai_filename = None
        if GEMINI_API_KEY:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info(f"Generating filename using router model: {FILENAME_MODEL}")
                ai_filename = generate_filename_from_ai(
                    topic, final_report, client, FILENAME_MODEL
                )
            except Exception as e:
                logger.warning(f"Filename model client failed, using fallback: {e}")
        else:
            logger.warning("GEMINI_API_KEY missing, using fallback filename")

        if not ai_filename:
            ai_filename = _fallback_filename(topic)

        filepath = CREATIONS_DIR / ai_filename
        base, ext = os.path.splitext(ai_filename)
        counter = 1
        while filepath.exists():
            filepath = CREATIONS_DIR / f"{base}_{counter}{ext}"
            counter += 1

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_report)

        try:
            update_agent_status(
                step=5, total_steps=5,
                thought="Report saved successfully.",
                action="deep_research", action_detail="COMPLETED"
            )
        except Exception:
            pass

        logger.info(f"Report saved to {filepath}")
        logger.info(f"Report automatically saved as: {filepath.name}")
        logger.info(f"Location: {CREATIONS_DIR.resolve()}")

        return final_report, str(filepath)

    except Exception as e:
        logger.error(f"Tavily Deep Research failed: {e}")
        return f"Error: {str(e)}", None


def deep_research_as_tool(topic: str) -> str:
    try:
        report, filepath = deep_research(topic)

        if filepath is None:
            return report

        filename = os.path.basename(filepath)
        return (
            f"Deep research completed successfully. Report saved as '{filename}' "
            f"at absolute path: {os.path.abspath(filepath)}. "
            f"Report length: {len(report)} characters."
        )
    except Exception as e:
        return f"Deep research failed: {str(e)}"


if __name__ == "__main__":
    query = input("Enter research topic: ")
    report, path = deep_research(query)
    print(f"\nSaved to: {path}" if path else f"\n{report}")