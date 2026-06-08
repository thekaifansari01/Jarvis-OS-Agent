import json
import os
import re
import datetime
from typing import Dict, Optional
from groq import Groq

from core.logger.logger import logger
from tools.workspace.workspace import workspace
from tools.OpenCloseApps.open_any import APP_PATHS, WEB_URLS
from core.brain.Processor.Prompts import SYSTEM_PROMPT
from core.brain.config import GROQ_FAST_MODEL, GROQ_API_KEY

from core.ui.typing_status import update_typing_status, launch_popup

USER_NAME = os.getenv("USER_NAME", "Bhai")
FAST_MODEL = GROQ_FAST_MODEL
ALL_OPEN_OPTIONS = list(APP_PATHS.keys()) + list(WEB_URLS.keys())

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def make_result(response, **kwargs):
    base = {
        "response": response, 
        "apps_to_open": [], 
        "apps_to_close": [], 
        "urls_to_open": [],
        "youtube_play": "", 
        "workspace_file_to_open": "", 
        "volume": {},           
        "brightness": {},       
        "system_action": "",    
        "priority": "high"
    }
    base.update(kwargs)
    return base

def clean_json_string(raw_text: str) -> str:
    json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if json_match: return json_match.group(1).strip()
    return re.sub(r'^```json\n|```$', '', raw_text, flags=re.MULTILINE).strip()

def build_fast_brain_prompt(raw_command: str, memory_instance=None, ephemeral: dict = None) -> str:
    available_apps = ALL_OPEN_OPTIONS
    current_time = datetime.datetime.now().strftime('%A, %d %B %Y | %I:%M %p')
    
    current_mood = "Neutral"
    if memory_instance and memory_instance.user_mood.get("mood_history"):
        current_mood = memory_instance.user_mood["mood_history"][-1]["mood"]
        
    user_info_block = f"\n[USER INFO]\nName: {USER_NAME}\nCurrent Mood: {current_mood}\n"
    
    fast_history = memory_instance.get_fast_history_context() if memory_instance else "No recent conversation."
    history_block = f"\n[RECENT CONVERSATION]\n{fast_history}\n"
    
    try:
        registry = workspace._load_registry()
        file_names = [f.get("filename") for f in registry.get("files", []) if f.get("filename")]
        files_str = ", ".join(file_names) if file_names else "No files in workspace."
    except Exception as e:
        logger.error(f"Failed to load lightweight registry: {e}")
        files_str = "Error loading files."
    workspace_block = f"\n[WORKSPACE FILES (ONLY NAMES)]\n{files_str}\n"

    ephemeral_block = ""
    if ephemeral:
        ephemeral_block = f"\n[RECENT AGENT ACTIVITY (USE THESE FOR 'OPEN THIS' COMMANDS)]\n"
        if ephemeral.get("last_found_links"):
            ephemeral_block += f"Links found earlier: {', '.join(ephemeral['last_found_links'])}\n"
        if ephemeral.get("last_generated_image"):
            ephemeral_block += f"Last generated image: {ephemeral['last_generated_image']}\n"
        if ephemeral.get("last_accessed_file"):
            ephemeral_block += f"Last file accessed: {ephemeral['last_accessed_file']}\n"
    
    return f"""[SYSTEM STATUS]\nTime: {current_time}{user_info_block}\n[AVAILABLE APPS]\n{", ".join(available_apps[:50])}...\n{history_block}{workspace_block}{ephemeral_block}\n[USER COMMAND]\n"{raw_command}"\nReturn STRICT JSON."""

def fetch_from_groq(raw_command: str, memory_instance=None, ephemeral: dict = None) -> Optional[Dict[str, any]]:
    if not groq_client: return None
    logger.info("笞｡ Routing to Fast Brain (Groq Llama Native Tools & Streaming)")
    
    result = {
        "response": "", "apps_to_open": [], "apps_to_close": [], "urls_to_open": [],
        "youtube_play": "", "workspace_file_to_open": "", 
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
                            "workspace_file_to_open": {"type": "string"},
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
                            "query": {"type": "string", "description": "The exact search query to look up on the web."}
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
        tool_call_name = ""
        tool_call_args = ""
        
        print("\n\033[96mJarvis:\033[0m ", end="", flush=True)

        for chunk in completion:
            delta = chunk.choices[0].delta
            if delta.content:
                final_text += delta.content
                print(delta.content, end="", flush=True)
                
                update_typing_status("typing", final_text)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.function.name:
                        tool_call_name += tc.function.name
                    if tc.function.arguments:
                        tool_call_args += tc.function.arguments

        print("\n")
        result["response"] = final_text.strip()

        if tool_call_name == "system_controller" and tool_call_args:
            try:
                args = json.loads(tool_call_args)
                result["apps_to_open"] = args.get("apps_to_open", [])
                result["apps_to_close"] = args.get("apps_to_close", [])
                result["urls_to_open"] = args.get("urls_to_open", [])
                result["youtube_play"] = args.get("youtube_play", "")
                result["workspace_file_to_open"] = args.get("workspace_file_to_open", "")
                result["volume"] = args.get("volume", {})
                result["brightness"] = args.get("brightness", {})
                result["system_action"] = args.get("system_action", "")
                
                if not result["response"]:
                    result["response"] = args.get("agent_reply", "Theek hai bhai, process kar raha hoon.")
            except Exception as e:
                logger.error(f"Error parsing Groq tool args: {e}")
            
        elif tool_call_name == "quick_web_search" and tool_call_args:
            try:
                args = json.loads(tool_call_args)
                result["quick_web_search"] = args.get("query", "")
                
                if not result["response"]:
                    result["response"] = args.get("agent_reply", "Ek second sir, check kar raha hoon...")
            except Exception as e:
                logger.error(f"Error parsing Groq tool args for search: {e}")

        update_typing_status("completed", result["response"])
        return result

    except Exception as e:
        logger.error(f"Fast Brain Error: {e}")
        update_typing_status("completed", f"Error aagaya bhai: {e}")
        return None