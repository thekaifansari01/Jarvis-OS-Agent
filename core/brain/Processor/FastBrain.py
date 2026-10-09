import json
import os
import re
import time
import datetime
import traceback
from typing import Dict, Optional, Tuple
import openai

from core.logger.logger import logger
from core.brain.Processor.Prompts import SYSTEM_PROMPT
from core.brain.config import FAST_BRAIN_API_KEY, FAST_BRAIN_MODEL, FAST_BRAIN_ENDPOINT
from core.ui.typing_status import update_typing_status, launch_popup
from core.ui.telegram_status import send_telegram_update, clear_telegram_context

USER_NAME = os.getenv("USER_NAME", "Sir")
FAST_MODEL = FAST_BRAIN_MODEL

fast_client = openai.OpenAI(
    api_key=FAST_BRAIN_API_KEY,
    base_url=FAST_BRAIN_ENDPOINT
) if FAST_BRAIN_API_KEY else None


def make_result(response, **kwargs):
    base = {
        "response": response,
        "apps_to_open": [],
        "apps_to_close": [],
        "urls_to_open": [],
        "youtube_play": "",
        "volume": {},
        "brightness": {},
        "system_action": "",
        "priority": "high"
    }
    base.update(kwargs)
    return base


def clean_json_string(raw_text: str) -> str:
    json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    return re.sub(r'^```json\n|```$', '', raw_text, flags=re.MULTILINE).strip()


def build_fast_brain_context(memory_instance=None, ephemeral: dict = None) -> str:
    current_time = datetime.datetime.now().strftime('%A, %d %B %Y | %I:%M %p')

    context = f"[[SYSTEM CONTEXT - DO NOT REVEAL THIS TO USER]]\n"
    context += f"Current Time: {current_time}\n"
    context += f"User Name: {USER_NAME}\n\n"

    fast_history = memory_instance.get_fast_history_context() if memory_instance else "No recent conversation."
    context += f"[[RECENT CONVERSATION]]\n{fast_history}\n\n"

    if ephemeral:
        context += "[[RECENT AGENT ACTIVITY]]\n"
        if ephemeral.get("last_found_links"):
            context += f"Links found earlier: {', '.join(ephemeral['last_found_links'])}\n"
        if ephemeral.get("last_generated_image"):
            context += f"Last generated image: {ephemeral['last_generated_image']}\n"

    return context


def _build_fast_brain_tools() -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": "system_controller",
                "description": "Use this tool to control system (volume, brightness, power, screenshot) or open/close apps and urls.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_reply": {
                            "type": "string",
                            "description": "A natural, contextual reply to the user confirming the action."
                        },
                        "apps_to_open": {"type": "array", "items": {"type": "string"}},
                        "apps_to_close": {"type": "array", "items": {"type": "string"}},
                        "urls_to_open": {"type": "array", "items": {"type": "string"}},
                        "youtube_play": {"type": "string"},
                        "volume": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string", "description": "'set', 'increase', 'decrease'"},
                                "value": {"type": "integer"}
                            }
                        },
                        "brightness": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string", "description": "'set', 'increase', 'decrease'"},
                                "value": {"type": "integer"}
                            }
                        },
                        "system_action": {"type": "string", "description": "'lock', 'sleep', 'screenshot'"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "quick_web_search",
                "description": "Use this ONLY for simple, real-time facts like current weather, sports scores, stock prices, or breaking news headlines.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_reply": {
                            "type": "string",
                            "description": "A quick acknowledgment (e.g., 'Checking the weather now...', 'One moment, checking live score...')."
                        },
                        "query": {
                            "type": "string",
                            "description": "Clean, concise search keywords (e.g., 'Mumbai weather today', 'IND vs AUS live score')."
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]


def _stream_completion(completion) -> Tuple[str, Dict[int, Dict[str, str]]]:
    buffer = ""
    tool_calls_map: Dict[int, Dict[str, str]] = {}
    last_ui_update = time.time()

    for chunk in completion:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta.content:
            buffer += delta.content
            now = time.time()
            if (now - last_ui_update) >= 0.08 or len(buffer) < 15:
                update_typing_status("typing", buffer)
                last_ui_update = now

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {"name": "", "arguments": ""}
                if tc.function:
                    if tc.function.name and not tool_calls_map[idx]["name"]:
                        tool_calls_map[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_map[idx]["arguments"] += tc.function.arguments

    return buffer, tool_calls_map


def _handle_system_controller(tool_args_str: str, result: dict) -> Optional[str]:
    try:
        args = json.loads(tool_args_str)
    except Exception as e:
        logger.error(f"❌ Failed to parse system_controller arguments: {e}\n{traceback.format_exc()}")
        return None

    result["apps_to_open"] = args.get("apps_to_open", []) or []
    result["apps_to_close"] = args.get("apps_to_close", []) or []
    result["urls_to_open"] = args.get("urls_to_open", []) or []
    result["youtube_play"] = args.get("youtube_play", "") or ""
    result["volume"] = args.get("volume", {}) or {}
    result["brightness"] = args.get("brightness", {}) or {}
    result["system_action"] = args.get("system_action", "") or ""

    logger.info(
        f"✅ system_controller parsed | "
        f"open={result['apps_to_open']} | close={result['apps_to_close']} | "
        f"urls={result['urls_to_open']} | yt='{result['youtube_play']}' | "
        f"vol={result['volume']} | bright={result['brightness']} | sys='{result['system_action']}'"
    )

    agent_reply = (args.get("agent_reply") or "").strip()
    return agent_reply if agent_reply else None


def _handle_quick_web_search(tool_args_str: str, raw_command: str) -> str:
    try:
        args = json.loads(tool_args_str)
    except Exception as e:
        logger.error(f"❌ Failed to parse quick_web_search arguments: {e}\n{traceback.format_exc()}")
        return "[sad] Sorry sir, search request parse nahi ho payi."

    query = (args.get("query") or "").strip()
    agent_reply = (args.get("agent_reply") or "One second, checking...").strip()

    if not query:
        logger.warning("⚠️ quick_web_search invoked with empty query")
        return "[sad] Sorry sir, search query empty tha."

    logger.info(f"🔍 Quick web search initiated | query='{query}'")
    update_typing_status("typing", agent_reply)

    try:
        from tools.SearchTools.WebSearch import quick_snippet_search
        search_data = quick_snippet_search(query, max_results=2)
        logger.info(f"✅ Snippets fetched | chars={len(str(search_data))}")
    except Exception as e:
        logger.error(f"❌ Quick web search failed: {e}\n{traceback.format_exc()}")
        return "[sad] Sorry sir, abhi real-time data check karne me dikkat aa rahi hai."

    try:
        final_completion = fast_client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are Jarvis. Provide a clear, natural Hinglish/English response using Markdown based ONLY on the user's query and the provided search snippets. DO NOT leak any metadata, tags, or mention that you searched."
                },
                {
                    "role": "user",
                    "content": f"User Query: {raw_command}\n\nSearch Snippets to use:\n{search_data}"
                }
            ],
            temperature=0.2,
            stream=True
        )
    except Exception as e:
        logger.error(f"❌ Quick search final completion failed: {e}\n{traceback.format_exc()}")
        return "[sad] Sorry sir, search result summarize nahi ho paya."

    final_answer = ""
    last_ui_update = time.time()
    for chunk in final_completion:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            final_answer += delta.content
            now = time.time()
            if (now - last_ui_update) >= 0.08 or len(final_answer) < 15:
                update_typing_status("typing", final_answer)
                last_ui_update = now

    logger.info(f"✅ Quick web search completed | query='{query}' | answer_chars={len(final_answer)}")
    return final_answer.strip()


def fetch_from_groq(raw_command: str, memory_instance=None, ephemeral: dict = None) -> Optional[Dict[str, any]]:
    if not fast_client:
        logger.error("❌ Fast Brain client not initialized. Check FAST_BRAIN_API_KEY.")
        return None

    logger.info(f"⚡ Fast Brain invoked | command='{raw_command[:80]}'")

    result = make_result("")

    try:
        system_context = build_fast_brain_context(memory_instance, ephemeral)
        tools = _build_fast_brain_tools()

        launch_popup()
        time.sleep(0.12)
        update_typing_status("typing", "...")

        messages = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{system_context}"},
            {"role": "user", "content": raw_command}
        ]

        logger.info(f"📤 Sending to Fast Brain | model={FAST_MODEL}")

        completion = fast_client.chat.completions.create(
            model=FAST_MODEL,
            messages=messages,
            temperature=0.2,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=True,
            stream=True
        )

        final_text, tool_calls_map = _stream_completion(completion)

        has_tool_calls = bool(tool_calls_map)
        logger.info(
            f"📥 Fast Brain stream complete | text_chars={len(final_text)} | tool_calls={len(tool_calls_map)}"
        )

        response_parts = []

        if has_tool_calls:
            for idx in sorted(tool_calls_map.keys()):
                tool_call = tool_calls_map[idx]
                tool_name = tool_call.get("name", "").strip()
                tool_args_str = (tool_call.get("arguments") or "").strip()

                if not tool_name:
                    logger.warning(f"⚠️ Empty tool name at index {idx}, skipping")
                    continue

                if not tool_args_str:
                    logger.warning(f"⚠️ Tool '{tool_name}' invoked with empty arguments, defaulting to {{}}")
                    tool_args_str = "{}"

                logger.info(f"🛠️ Executing tool call [{idx + 1}/{len(tool_calls_map)}]: {tool_name}")

                if tool_name == "system_controller":
                    agent_reply = _handle_system_controller(tool_args_str, result)
                    if agent_reply:
                        response_parts.append(agent_reply)

                elif tool_name == "quick_web_search":
                    search_response = _handle_quick_web_search(tool_args_str, raw_command)
                    if search_response:
                        response_parts.append(search_response)

                else:
                    logger.warning(f"⚠️ Unknown tool call from Fast Brain: {tool_name}")

        final_text_stripped = final_text.strip()

        if response_parts:
            result["response"] = "\n\n".join(response_parts)
        elif has_tool_calls:
            result["response"] = final_text_stripped or "Processing your request."
        else:
            result["response"] = final_text_stripped

        if result["response"]:
            print(f"\n\033[96mJarvis:\033[0m {result['response']}\n", flush=True)
        else:
            print("\n\033[96mJarvis:\033[0m [silent execution]\n", flush=True)

        logger.info(
            f"✅ Fast Brain final response ready | chars={len(result['response'])} | "
            f"open={len(result['apps_to_open'])} close={len(result['apps_to_close'])} "
            f"urls={len(result['urls_to_open'])} sys='{result['system_action']}'"
        )

        update_typing_status("completed", result["response"])
        send_telegram_update(final_response=result["response"])
        clear_telegram_context()
        return result

    except Exception as e:
        logger.error(f"❌ Fast Brain fatal error: {e}\n{traceback.format_exc()}")
        err_msg = "Bhai, Fast Brain me kuch gadbad ho gayi. Please try again."
        update_typing_status("completed", err_msg)
        send_telegram_update(final_response=err_msg)
        clear_telegram_context()
        return None