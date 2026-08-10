import json
import os
import re
import time
import datetime
from typing import Dict, Optional
from groq import Groq

from core.logger.logger import logger
from core.brain.Processor.Prompts import SYSTEM_PROMPT
from core.brain.config import GROQ_FAST_MODEL, GROQ_API_KEY
from core.ui.typing_status import update_typing_status, launch_popup

USER_NAME = os.getenv("USER_NAME", "Sir")
FAST_MODEL = GROQ_FAST_MODEL

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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

def fetch_from_groq(raw_command: str, memory_instance=None, ephemeral: dict = None) -> Optional[Dict[str, any]]:
    if not groq_client:
        return None
    logger.info("⚡ Routing to Fast Brain (Groq Llama Native Tools & Streaming)")
    
    result = make_result("")
    
    try:
        system_context = build_fast_brain_context(memory_instance, ephemeral)
        
        tools = [
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

        launch_popup()
        time.sleep(0.12)
        update_typing_status("typing", "...")

        messages = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{system_context}"}, 
            {"role": "user", "content": raw_command}
        ]

        completion = groq_client.chat.completions.create(
            model=FAST_MODEL,
            messages=messages,
            temperature=0.2,
            tools=tools,
            tool_choice="auto",
            stream=True
        )
        
        final_text = ""
        tool_calls_map = {}
        last_ui_update = time.time()
        
        print("\n\033[96mJarvis:\033[0m ", end="", flush=True)

        for chunk in completion:
            delta = chunk.choices[0].delta
            if delta.content:
                final_text += delta.content
                print(delta.content, end="", flush=True)
                
                now = time.time()
                if (now - last_ui_update) >= 0.08 or len(final_text) < 15:
                    update_typing_status("typing", final_text)
                    last_ui_update = now

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"name": "", "arguments": ""}
                    if tc.function.name:
                        tool_calls_map[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_map[idx]["arguments"] += tc.function.arguments

        update_typing_status("typing", final_text)
        print("\n")
        result["response"] = final_text.strip()

        tool_call_name = ""
        tool_call_args = ""
        if tool_calls_map:
            first_idx = sorted(tool_calls_map.keys())[0]
            tool_call_name = tool_calls_map[first_idx]["name"]
            tool_call_args = tool_calls_map[first_idx]["arguments"]

        if tool_call_name == "system_controller" and tool_call_args:
            try:
                args = json.loads(tool_call_args)
                result["apps_to_open"] = args.get("apps_to_open", [])
                result["apps_to_close"] = args.get("apps_to_close", [])
                result["urls_to_open"] = args.get("urls_to_open", [])
                result["youtube_play"] = args.get("youtube_play", "")
                result["volume"] = args.get("volume", {})
                result["brightness"] = args.get("brightness", {})
                result["system_action"] = args.get("system_action", "")
                
                if not result["response"]:
                    result["response"] = args.get("agent_reply", "Processing your request.")
            except Exception as e:
                logger.error(f"Error parsing Groq tool args: {e}")

        elif tool_call_name == "quick_web_search" and tool_call_args:
            try:
                from tools.SearchTools.WebSearch import quick_snippet_search
                
                args = json.loads(tool_call_args)
                query = args.get("query", "")
                agent_reply = args.get("agent_reply", "One second, checking...")
                
                update_typing_status("typing", agent_reply)
                
                search_data = quick_snippet_search(query, max_results=2)
                
                print("\n\033[96mJarvis (Quick Search):\033[0m ", end="", flush=True)
                
                final_completion = groq_client.chat.completions.create(
                    model=FAST_MODEL,
                    messages=[
                        {"role": "system", "content": "You are Jarvis. Provide a clear, natural Hinglish/English response using Markdown based ONLY on the user's query and the provided search snippets. DO NOT leak any metadata, tags, or mention that you searched."},
                        {"role": "user", "content": f"User Query: {raw_command}\n\nSearch Snippets to use:\n{search_data}"}
                    ],
                    temperature=0.2,
                    stream=True
                )
                
                final_answer = ""
                last_ui_update = time.time()
                for chunk in final_completion:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        final_answer += delta.content
                        print(delta.content, end="", flush=True)
                        now = time.time()
                        if (now - last_ui_update) >= 0.08 or len(final_answer) < 15:
                            update_typing_status("typing", final_answer)
                            last_ui_update = now
                
                update_typing_status("typing", final_answer)
                print("\n")
                result["response"] = final_answer.strip()
                
            except Exception as e:
                logger.error(f"Quick Search Error: {e}")
                result["response"] = "[sad] Sorry sir, abhi real-time data check karne me dikkat aa rahi hai."

        update_typing_status("completed", result["response"])
        return result

    except Exception as e:
        logger.error(f"Fast Brain Error: {e}")
        update_typing_status("completed", f"Error occurred: {e}")
        return None