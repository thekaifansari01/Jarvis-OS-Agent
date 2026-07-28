import json
import os
import re
import time
import tempfile
import datetime
from typing import Dict, Optional

from groq import Groq
from google import genai
from google.genai import types

from core.brain.config import CONFIG
from core.logger.logger import logger
from core.brain.executor import execute_single_tool_sync
from core.ui.agent_status import update_agent_status
from core.brain.config import (
    GROQ_FAST_MODEL, GEMINI_AGENT_MODEL, 
    GROQ_API_KEY, GEMINI_API_KEY 
)

from core.brain.Processor.Prompts import AGENT_SYSTEM_PROMPT, get_native_tools
from core.brain.Processor.FastBrain import make_result, clean_json_string

from core.ui.typing_status import launch_popup, update_typing_status

FAST_MODEL = GROQ_FAST_MODEL
AGENT_MODEL_GEMINI = GEMINI_AGENT_MODEL

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def run_agentic_loop(raw_command: str, context: str, memory_instance=None) -> Dict[str, any]:
    logger.info(f"🤖 AGENTIC LOOP INITIATED (Gemini {AGENT_MODEL_GEMINI} - MISSION-ANCHORED REACT MODE)...")
    
    recent_context_xml = memory_instance.get_agentic_fast_context() if memory_instance else "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
    
    scratchpad = f"""<Mission>
User Command: "{raw_command}"
</Mission>

{recent_context_xml}

<Thought_Trail>
"""
    
    max_steps = CONFIG.get("AGENT_MAX_STEPS", 10)
    timeout_seconds = CONFIG.get("AGENT_TIMEOUT", 120)
    retry_limit = CONFIG.get("AGENT_RETRY_LIMIT", 2)
    step = 0
    start_time = time.time()
    
    completed_actions = set()
    
    metadata_tracker = {
        "apps_opened": [],
        "apps_closed": [],
        "files_touched": [],
        "system_events": []
    }

    if memory_instance and not hasattr(memory_instance, 'ephemeral'):
        memory_instance.ephemeral = {}
    ephemeral = memory_instance.ephemeral if memory_instance else {}

    native_tools = get_native_tools()

    while step < max_steps:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            logger.warning(f"⏰ Agent loop timeout after {elapsed:.1f} seconds")
            update_agent_status(step=0, total_steps=max_steps, thought="Task timed out", action="", action_detail="")
            
            timeout_msg = "Bhai, task thoda zyada time le raha tha, timeout ho gaya. Aap phir se try karo ya simple command do."
            launch_popup()
            update_typing_status("completed", timeout_msg)
            return make_result(timeout_msg, priority="high", agent_executed=True)

        logger.info(f"🔄 Agent Loop Step {step + 1}/{max_steps}")
        current_time = datetime.datetime.now().strftime('%A, %d %B %Y | %I:%M %p')

        live_feedback = ""
        override_block = "[⚡ LIVE OVERRIDES]\nNone"
        
        if memory_instance and hasattr(memory_instance, 'get_and_clear_feedback'):
            live_feedback = memory_instance.get_and_clear_feedback()
            
        if live_feedback:
            logger.warning(f"🚨 User injected live feedback: {live_feedback}")
            override_block = f"[⚡ LIVE OVERRIDES]\n🛑 CRITICAL USER UPDATE: {live_feedback}"
            scratchpad += f"\n[⚡ SYSTEM EVENT: User provided live feedback -> '{live_feedback}'. Adapting strategy.]\n"

        panic_warning = f"⚠️ WARNING: You are running out of steps! Execute final action NOW." if step + 1 >= max_steps - 1 else ""
        completed_list = "\n".join([f"- {act}" for act in completed_actions]) if completed_actions else "None yet."
        
        ephemeral_prompt = ""
        if ephemeral.get("last_found_links"):
            ephemeral_prompt += f"\n[EPHEMERAL: Last found links = {ephemeral['last_found_links']}]"
        if ephemeral.get("last_generated_image"):
            ephemeral_prompt += f"\n[EPHEMERAL: Last generated image = {ephemeral['last_generated_image']}]"
        if ephemeral.get("last_screenshot"):
            ephemeral_prompt += f"\n[EPHEMERAL: Last screenshot taken = {ephemeral['last_screenshot']}]"
        if ephemeral.get("last_contact"):
            ephemeral_prompt += f"\n[EPHEMERAL: Last contacted person/email = {ephemeral['last_contact']}]"

        prompt = f"""[SYSTEM STATUS]
Time: {current_time}
[BUDGET TRACKER]
Current Step: {step + 1} out of {max_steps}. {panic_warning}

[COMPLETED ACTIONS (DO NOT REPEAT)]
{completed_list}

[MEMORY & CONTEXT]
{context}

{ephemeral_prompt}

{override_block}

[SCRATCHPAD]
{scratchpad}

=========================================
[🛑 CURRENT STATE & DIRECTIVE]
Based on the <Mission>, [LIVE OVERRIDES], and the <Thought_Trail> above, determine your absolute next step natively.
If the <Mission> is fully complete, call 'complete_task'.
"""

        try:
            update_agent_status(
                step=step+1,
                total_steps=max_steps,
                thought="Thinking...",
                action="THINKING",
                action_detail=""
            )

            ai_response = {}
            max_api_retries = 10
            
            for attempt in range(max_api_retries):
                try:
                    if gemini_client:
                        panic_step = max_steps - 2
                        full_prompt = AGENT_SYSTEM_PROMPT.format(max_steps=max_steps, panic_step=panic_step) + "\n\n" + prompt
                        
                        contents_payload = [full_prompt]

                        response = gemini_client.models.generate_content(
                            model=AGENT_MODEL_GEMINI,
                            contents=contents_payload,
                            config=types.GenerateContentConfig(
                                temperature=0.1,
                                tools=native_tools
                            )
                        )
                        
                        thought_text = "Analyzing context natively..."
                        
                        if response.candidates and response.candidates[0].content.parts:
                            for part in response.candidates[0].content.parts:
                                if part.text:
                                    thought_text = part.text.strip()
                                elif part.function_call:
                                    func_name = part.function_call.name
                                    func_args = dict(part.function_call.args) if part.function_call.args else {}
                                    
                                    if func_name == "complete_task":
                                        ai_response["is_task_complete"] = True
                                        ai_response["response"] = func_args.get("response", "Task completed sir.")
                                    else:
                                        ai_response[func_name] = func_args
                        
                        ai_response["thought"] = thought_text

                    else:
                        panic_step = max_steps - 2
                        full_prompt = AGENT_SYSTEM_PROMPT.format(max_steps=max_steps, panic_step=panic_step)
                        completion = groq_client.chat.completions.create(
                            model=FAST_MODEL,
                            messages=[{"role": "system", "content": full_prompt}, {"role": "user", "content": prompt}],
                            temperature=0.2,
                            response_format={"type": "json_object"}
                        )
                        ai_response = json.loads(clean_json_string(completion.choices[0].message.content.strip()))
                    
                    break
                    
                except Exception as api_err:
                    error_msg = str(api_err)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                        raise api_err 
                    if attempt < max_api_retries - 1:
                        logger.warning(f"⚠️ API Generation failed (Attempt {attempt + 1}/{max_api_retries}): {api_err}. Retrying in 2 seconds...")
                        time.sleep(2)
                    else:
                        logger.error(f"❌ API failed completely after {max_api_retries} attempts.")
                        raise api_err 
            
            logger.info(f"🧠 Agent Thought: {ai_response.get('thought', 'Thinking...')}")
            
            ignore_keys = ["thought", "is_task_complete", "response"]
            action_key = ""
            action_detail = ""

            if ai_response:
                for key, value in ai_response.items():
                    if key not in ignore_keys:
                        action_key = key
                        if key == "memory_actions" and isinstance(value, dict):
                            if value.get("recent_logs"):
                                action_detail = "Fetching 15-Day Recent Logs"
                            elif value.get("lifetime_recall"):
                                action_detail = f"Recalling LTM: {value.get('lifetime_recall')}"
                        elif key == "search_actions" and isinstance(value, dict):
                            action_detail = value.get("web", "") or value.get("youtube", "") or value.get("arxiv", "") or value.get("vault", "") or value.get("read_webpage", "")
                        elif key == "execute_terminal_command" and isinstance(value, dict):
                            action_detail = value.get("command", "")
                        elif key == "run_python_code" and isinstance(value, dict):
                            code = value.get("code_string", "").strip()
                            action_detail = code.split("\n")[0][:60] if code else "Running Script"
                        elif key == "deep_research" and isinstance(value, dict):
                            action_detail = value.get("topic", "")
                        elif key == "email_action" and isinstance(value, dict):
                            action_detail = f"To: {value.get('to', '')}"
                        elif key == "whatsapp_action" and isinstance(value, dict):
                            action_detail = f"To: {value.get('to', '')}"
                        elif key == "image_command" and isinstance(value, dict):
                            action_detail = value.get("prompt", "")
                        elif key == "calendar_action" and isinstance(value, dict):
                            action_detail = f"{value.get('action', '').capitalize()} Calendar"
                        elif key == "clipboard_action" and isinstance(value, dict):
                            action_detail = f"{value.get('action', '').upper()} Clipboard"
                        elif key == "system_controller" and isinstance(value, dict):
                            if value.get("system_action") == "screenshot":
                                action_detail = "Capturing Screen..."
                            else:
                                action_detail = "Controlling System"
                        break

            update_agent_status(
                step=step+1,
                total_steps=max_steps,
                thought=ai_response.get('thought', ''),
                action=action_key,
                action_detail=action_detail
            )

            if ai_response.get("is_task_complete"):
                logger.info("✅ Agent declared task complete!")
                final_text = ai_response.pop("response", "Task completed sir.")
                
                sys_ctrl = ai_response.get("system_controller", {})
                if sys_ctrl.get("urls_to_open"):
                    ephemeral["last_found_links"] = sys_ctrl["urls_to_open"]
                if ai_response.get("image_command", {}).get("filename"):
                    ephemeral["last_generated_image"] = ai_response["image_command"]["filename"]
                
                update_agent_status(step=0, total_steps=max_steps, thought="Task completed", action="", action_detail="")
                
                launch_popup()
                update_typing_status("completed", final_text)
                
                return make_result(final_text, is_agentic=True, agent_executed=True, metadata=metadata_tracker, **ai_response)

            observation = None
            for attempt in range(retry_limit):
                try:
                    if action_key == "memory_actions":
                        mem_data = ai_response.get("memory_actions", {})
                        
                        if mem_data.get("recent_logs"):
                            if memory_instance:
                                logger.info("🧠 Agent requested full 15-day Chat History log natively.")
                                history_data = memory_instance.get_chat_history_for_tool()
                                observation = f"Observation: Successfully retrieved full 15-day history logs:\n\n{history_data}"
                            else:
                                observation = "Observation: Error -> Memory system instance is offline."
                                
                        elif mem_data.get("lifetime_recall"):
                            query = mem_data.get("lifetime_recall")
                            logger.info(f"🧠 Agent requesting LTM Recall for: {query}")
                            try:
                                from core.brain.Memory.LifetimeMemory import ltm_engine
                                observation = ltm_engine.search_lifetime_memory(query)
                            except Exception as e:
                                logger.error(f"❌ LTM Recall tool crashed: {e}")
                                observation = f"Observation: LTM Recall error -> {e}"
                        else:
                            observation = "Observation: No valid memory target provided. Use 'recent_logs' or 'lifetime_recall'."
                    
                    elif action_key and action_key != "THINKING":
                        observation = execute_single_tool_sync(ai_response)
                    
                    if observation:
                        if action_key in ["email_action", "whatsapp_action"]:
                            ephemeral["last_contact"] = ai_response.get(action_key, {}).get("to", "")

                        if "http" in observation and "link" in observation.lower():
                            urls = re.findall(r'https?://[^\s]+', observation)
                            if urls:
                                ephemeral["last_found_links"] = urls[:3]
                        if "file" in observation.lower() and (".png" in observation or ".md" in observation or ".txt" in observation or ".jpg" in observation):
                            file_match = re.search(r'([\w\-:\\/.]+\.(png|md|txt|jpg))', observation)
                            if file_match:
                                ephemeral["last_accessed_file"] = file_match.group(1)
                    
                    obs_prefix = str(observation).lower()[:50]
                    if observation and ("error" not in obs_prefix and "❌" not in obs_prefix and "failed" not in obs_prefix):
                        action_fingerprint = f"{action_key}:{str(ai_response.get(action_key, ''))[:100]}"
                        completed_actions.add(action_fingerprint)
                        
                        try:
                            if action_key == "system_controller":
                                sys_data = ai_response.get("system_controller", {})
                                if sys_data.get("apps_to_open"): metadata_tracker["apps_opened"].extend(sys_data["apps_to_open"])
                                if sys_data.get("apps_to_close"): metadata_tracker["apps_closed"].extend(sys_data["apps_to_close"])
                                if sys_data.get("urls_to_open"): metadata_tracker["system_events"].append(f"Opened URLs: {', '.join(sys_data['urls_to_open'])}")
                                if sys_data.get("system_action"): metadata_tracker["system_events"].append(f"System Action: {sys_data['system_action']}")
                            
                                if sys_data.get("system_action") == "screenshot" and sys_data.get("screenshot_filename"):
                                    ephemeral["last_screenshot"] = sys_data.get("screenshot_filename")

                            elif action_key == "execute_terminal_command":
                                cmd_data = ai_response.get("execute_terminal_command", {})
                                metadata_tracker["system_events"].append(f"Terminal Command: {cmd_data.get('command', '')}")

                            elif action_key == "run_python_code":
                                metadata_tracker["system_events"].append("Executed Python Code Script")
                            
                            else:
                                metadata_tracker["system_events"].append(f"Executed {action_key}: {action_detail}")
                                
                        except Exception as meta_err:
                            logger.error(f"⚠️ Error tracking metadata: {meta_err}")

                        update_agent_status(
                            step=step+1,
                            total_steps=max_steps,
                            thought=ai_response.get('thought', ''),
                            action=action_key,
                            action_detail=action_detail,
                            observation=observation[:200]
                        )
                        break
                    elif attempt < retry_limit - 1:
                        logger.warning(f"⚠️ Tool attempt {attempt+1} failed: {observation}. Retrying in 2s...")
                        time.sleep(2)
                except Exception as tool_err:
                    observation = f"Observation: Tool execution error - {tool_err}"
                    if attempt < retry_limit - 1: time.sleep(2)
            else:
                observation = f"Observation: Tool failed after {retry_limit} retries. Try a different approach."

            thought_str = ai_response.get('thought', 'Thinking...')
            action_str = f"{action_key} ({action_detail})" if action_key else "None (Missed Tool Call)"
            
            scratchpad += f"""
<Step number="{step+1}">
  <Thought>{thought_str}</Thought>
  <Executed_Tool>{action_str}</Executed_Tool>
  <Result>{observation}</Result>
</Step>
"""
            
            step += 1
            time.sleep(1)

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                logger.error("❌ Gemini API Rate Limit (429) Hit!")
                update_agent_status(step=0, total_steps=max_steps, thought="Rate limit exceeded", action="", action_detail="")
                
                limit_msg = "Bhai, Google Gemini ki free API speed limit khatam ho gayi hai. 60 seconds ruko aur phir try karo."
                launch_popup()
                update_typing_status("completed", limit_msg)
                return make_result(limit_msg, priority="high", agent_executed=True)
            
            logger.error(f"❌ Agent Loop Error (API/Crash): {e}")
            time.sleep(3)

            scratchpad += f"""
<Step number="{step+1}">
  <Thought>System crash handled.</Thought>
  <Executed_Tool>System Error</Executed_Tool>
  <Result>{e}. Skipping this step.</Result>
</Step>
"""
            step += 1

    update_agent_status(step=0, total_steps=max_steps, thought="Max steps reached", action="", action_detail="")
    
    limit_msg = f"Bhai, maine maximum steps ({max_steps}) le liye hain. Task loop limit tak pahunch gaya hai. Kripya simple command do."
    launch_popup()
    update_typing_status("completed", limit_msg)
    
    return make_result(limit_msg, priority="high", agent_executed=True, metadata=metadata_tracker)