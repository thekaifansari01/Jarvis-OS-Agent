import json
import os
import re
import datetime
from typing import Dict, Optional
from groq import Groq

from core.logger.logger import logger
from core.brain.Processor.Prompts import SYSTEM_PROMPT
from core.brain.config import GROQ_FAST_MODEL, GROQ_API_KEY

from core.ui.typing_status import update_typing_status, launch_popup

USER_NAME = os.getenv("USER_NAME", "Bhai")
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

def build_fast_brain_prompt(raw_command: str, memory_instance=None, ephemeral: dict = None) -> str:
    current_time = datetime.datetime.now().strftime('%A, %d %B %Y | %I:%M %p')
    
    current_mood = "Neutral"
    if memory_instance and memory_instance.user_mood.get("mood_history"):
        current_mood = memory_instance.user_mood["mood_history"][-1]["mood"]
        
    user_info_block = f"\n[USER INFO]\nName: {USER_NAME}\nCurrent Mood: {current_mood}\n"
    
    fast_history = memory_instance.get_fast_history_context() if memory_instance else "No recent conversation."
    history_block = f"\n[RECENT CONVERSATION]\n{fast_history}\n"

    ephemeral_block = ""
    if ephemeral:
        ephemeral_block = "\n[RECENT AGENT ACTIVITY (USE THESE FOR 'OPEN THIS' COMMANDS)]\n"
        if ephemeral.get("last_found_links"):
            ephemeral_block += f"Links found earlier: {', '.join(ephemeral['last_found_links'])}\n"
        if ephemeral.get("last_generated_image"):
            ephemeral_block += f"Last generated image: {ephemeral['last_generated_image']}\n"
    
    return f"[SYSTEM STATUS]\nTime: {current_time}{user_info_block}\n[AVAILABLE APPS]\nYou can open/close ANY standard Windows App or popular Website. The system handles indexing dynamically.\n{history_block}{ephemeral_block}\n[USER COMMAND]\n\"{raw_command}\"\nReturn STRICT JSON."

def fetch_from_groq(raw_command: str, memory_instance=None, ephemeral: dict = None) -> Optional[Dict[str, any]]:
    if not groq_client:
        return None
    logger.info("⚡ Routing to Fast Brain (Groq Llama Native Tools & Streaming)")
    
    result = {
        "response": "", "apps_to_open": [], "apps_to_close": [], "urls_to_open": [],
        "youtube_play": "",
        "volume": {}, "brightness": {}, "system_action": "",
        "priority": "high"
    }
    
    try:
        dynamic_prompt = build_fast_brain_prompt(raw_command, memory_instance, ephemeral)
        dynamic_prompt = dynamic_prompt.replace("\nReturn STRICT JSON.", "")

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
                                "description": "A natural, contextual Hinglish reply to the user confirming the action (e.g., 'Theek hai bhai, system lock kar diya', 'Aap aao tab tak lock rakhta hoon', 'Volume badha di bhai')."
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
                    "description": "Use this to search the web for simple, real-time facts (weather, scores, news).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_reply": {
                                "type": "string",
                                "description": "A natural, contextual Hinglish reply to the user acknowledging the search (e.g., 'Ek second bhai, online check kar raha hoon', 'Mausam ka haal abhi batata hoon')."
                            },
                            "query": {
                                "type": "string",
                                "description": "The exact SEO-optimized search keywords to look up on Google. MUST be clean English/Hinglish keywords (e.g., 'Mumbai weather today forecast', 'IPL live score'). NEVER pass long conversational sentences."
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        launch_popup()
        update_typing_status("typing", "")

        completion = groq_client.chat.completions.create(
            model=FAST_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": dynamic_prompt}],
            temperature=0.3,
            tools=tools,
            tool_choice="auto",
            stream=True
        )
        
        final_text = ""
        tool_calls_map = {}
        
        print("\n\033[96mJarvis:\033[0m ", end="", flush=True)

        for chunk in completion:
            delta = chunk.choices[0].delta
            if delta.content:
                final_text += delta.content
                print(delta.content, end="", flush=True)
                update_typing_status("typing", final_text)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"name": "", "arguments": ""}
                    if tc.function.name:
                        tool_calls_map[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_map[idx]["arguments"] += tc.function.arguments

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
                    result["response"] = args.get("agent_reply", "Theek hai bhai, process kar raha hoon.")
            except Exception as e:
                logger.error(f"Error parsing Groq tool args: {e}")
            
        elif tool_call_name == "quick_web_search" and tool_call_args:
            try:
                from tools.SearchTools.WebSearch import search_web
                
                args = json.loads(tool_call_args)
                query = args.get("query", "")
                agent_reply = args.get("agent_reply", "Ek second sir, check kar raha hoon...")
                
                update_typing_status("typing", agent_reply)
                
                search_xml = search_web(query, max_results=2)
                context_prompt = build_fast_brain_prompt(raw_command, memory_instance, ephemeral)
                
                print("\n\033[96mJarvis (Web Search):\033[0m ", end="", flush=True)
                
                final_completion = groq_client.chat.completions.create(
                    model=FAST_MODEL,
                    messages=[
                        {"role": "system", "content": f"You are Jarvis. Answer the user's query naturally in Hinglish based ONLY on the provided Search Data and user context. Be direct, helpful, and do not use markdown.\n{context_prompt}"},
                        {"role": "user", "content": f"Query: {raw_command}\nSearch Data: {search_xml[:4000]}"}
                    ],
                    temperature=0.3,
                    stream=True
                )
                
                final_answer = ""
                for chunk in final_completion:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        final_answer += delta.content
                        print(delta.content, end="", flush=True)
                        update_typing_status("typing", final_answer)
                
                print("\n")
                result["response"] = final_answer.strip()
                
            except Exception as e:
                logger.error(f"Error parsing Groq tool args for search: {e}")
                result["response"] = "Sorry sir, search data process karne mein error aa gaya."

        update_typing_status("completed", result["response"])
        return result

    except Exception as e:
        logger.error(f"Fast Brain Error: {e}")
        update_typing_status("completed", f"Error aagaya bhai: {e}")
        return None