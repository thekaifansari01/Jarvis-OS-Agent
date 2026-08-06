import json
import os
import re
import time
import tempfile
import datetime
from typing import Dict, Optional
import tiktoken
from core.brain.config import CONFIG
from core.logger.logger import logger
from core.brain.executor import execute_single_tool_sync
from core.ui.agent_status import update_agent_status
from core.brain.config import (
    GROQ_FAST_MODEL,
    AGENT_PRIMARY_PROVIDER,
    AGENT_FALLBACK_PROVIDER,
)
from core.brain.Providers import get_provider
from core.brain.Processor.Prompts import AGENT_SYSTEM_PROMPT, get_native_tools
from core.brain.Processor.FastBrain import make_result, clean_json_string
from core.ui.typing_status import launch_popup, update_typing_status

FAST_MODEL = GROQ_FAST_MODEL

try:
    TOKENIZER = tiktoken.get_encoding("cl100k_base")
except Exception:
    TOKENIZER = None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if TOKENIZER:
        try:
            return len(TOKENIZER.encode(str(text)))
        except Exception:
            pass
    return len(str(text)) // 4


def optimize_observation(text: str, max_chars: int = 10000) -> str:
    if not text:
        return "Observation: Empty result."
    text_str = str(text)
    if len(text_str) <= max_chars:
        return text_str
    
    if "Vault Search Results" in text_str:
        lines = text_str.split('\n')
        metadata_lines = []
        content_lines = []
        in_content = False
        for line in lines:
            if "CONTENT:" in line:
                in_content = True
                metadata_lines.append(line)
                continue
            if in_content:
                content_lines.append(line)
            else:
                metadata_lines.append(line)
        
        metadata_str = "\n".join(metadata_lines)
        content_str = "\n".join(content_lines)
        
        if len(metadata_str) + len(content_str) <= max_chars:
            return text_str
        
        half = (max_chars - len(metadata_str) - 50) // 2
        if half > 0:
            content_truncated = f"{content_str[:half]}\n...[TRUNCATED {len(content_str) - (half*2)} CHARS]...\n{content_str[-half:]}"
        else:
            content_truncated = content_str[:100] + "...[TRUNCATED]..."
        
        return metadata_str + "\n" + content_truncated
    
    half = max_chars // 2
    return (
        f"{text_str[:half]}\n...[TRUNCATED {len(text_str) - max_chars} CHARS]...\n{text_str[-half:]}"
    )


def update_confirmed_facts(
    facts_ledger: Dict[str, str], action_key: str, action_detail: str, observation: str
) -> None:
    obs_str = str(observation).strip()
    if not obs_str or "error" in obs_str.lower() or "failed" in obs_str.lower():
        return

    if action_key == "execute_terminal_command":
        facts_ledger[f"Terminal ({action_detail[:30]})"] = (
            obs_str[:150].replace("\n", " ").strip()
        )
    elif action_key == "search_actions":
        facts_ledger[f"Search ({action_detail[:30]})"] = (
            obs_str[:150].replace("\n", " ").strip()
        )
    elif action_key == "file_operations":
        facts_ledger[f"File Op ({action_detail[:30]})"] = (
            obs_str[:100].replace("\n", " ").strip()
        )
    elif action_key == "run_python_code":
        facts_ledger["Last Python Output"] = obs_str[:150].replace("\n", " ").strip()


def run_agentic_loop(
    raw_command: str, context: str, memory_instance=None, silent: bool = False
) -> Dict[str, any]:
    logger.info(
        f"🤖 AGENTIC LOOP INITIATED (Provider: {AGENT_PRIMARY_PROVIDER} | Fallback: {AGENT_FALLBACK_PROVIDER})..."
    )
    try:
        primary_provider = get_provider(AGENT_PRIMARY_PROVIDER)
        fallback_provider = get_provider(AGENT_FALLBACK_PROVIDER)
        current_provider = primary_provider
        logger.info(f"✅ Primary provider loaded: {AGENT_PRIMARY_PROVIDER}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize primary provider: {e}")
        try:
            current_provider = get_provider(AGENT_FALLBACK_PROVIDER)
            logger.info(f"🔄 Using fallback provider: {AGENT_FALLBACK_PROVIDER}")
        except Exception as e2:
            logger.error(f"❌ All providers failed to initialize: {e2}")
            return make_result(
                "Bhai, AI provider start nahi ho pa raha. Check API keys.",
                priority="high",
            )

    recent_context_xml = (
        memory_instance.get_agentic_fast_context()
        if memory_instance
        else "<Recent_Context>\nNo recent conversation.\n</Recent_Context>"
    )

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
    total_loop_tokens = 0
    start_time = time.time()

    completed_actions = set()
    confirmed_facts = {}
    pending_image_payloads = []

    metadata_tracker = {
        "apps_opened": [],
        "apps_closed": [],
        "files_touched": [],
        "system_events": [],
    }

    if memory_instance and not hasattr(memory_instance, "ephemeral"):
        memory_instance.ephemeral = {}
    ephemeral = memory_instance.ephemeral if memory_instance else {}

    native_tools = get_native_tools()

    while step < max_steps:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            logger.warning(f"⏰ Agent loop timeout after {elapsed:.1f} seconds")
            if not silent:
                update_agent_status(
                    step=0,
                    total_steps=max_steps,
                    thought="Task timed out",
                    action="",
                    action_detail="",
                    tokens=total_loop_tokens,
                )
                timeout_msg = "Task was taking too long and timed out. Please try again or provide a simpler command."
                launch_popup()
                update_typing_status("completed", timeout_msg)
            else:
                timeout_msg = "Background task timeout."
            return make_result(
                timeout_msg, priority="high", agent_executed=True
            )

        logger.info(
            f"🔄 Agent Loop Step {step + 1}/{max_steps} (Provider: {current_provider.__class__.__name__})"
        )
        current_time = datetime.datetime.now().strftime("%A, %d %B %Y | %I:%M %p")

        live_feedback = ""
        override_block = "[⚡ LIVE OVERRIDES]\nNone"

        if memory_instance and hasattr(memory_instance, "get_and_clear_feedback"):
            live_feedback = memory_instance.get_and_clear_feedback()

        if live_feedback:
            logger.warning(f"🚨 User injected live feedback: {live_feedback}")
            override_block = (
                f"[⚡ LIVE OVERRIDES]\n🛑 CRITICAL USER UPDATE: {live_feedback}"
            )
            scratchpad += f"\n[⚡ SYSTEM EVENT: User provided live feedback -> '{live_feedback}'. Adapting strategy.]\n"

        panic_warning = (
            f"⚠️ WARNING: You are running out of steps! Execute final action NOW."
            if step + 1 >= max_steps - 1
            else ""
        )
        completed_list = (
            "\n".join([f"- {act}" for act in completed_actions])
            if completed_actions
            else "None yet."
        )

        facts_list = (
            "\n".join([f"- {k}: {v}" for k, v in confirmed_facts.items()])
            if confirmed_facts
            else "No confirmed facts pinned yet."
        )

        ephemeral_prompt = ""
        if ephemeral.get("last_found_links"):
            ephemeral_prompt += (
                f"\n[EPHEMERAL: Last found links = {ephemeral['last_found_links']}]"
            )
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

<Confirmed_Facts>
{facts_list}
</Confirmed_Facts>

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
Based on the <Mission>, <Confirmed_Facts>, [LIVE OVERRIDES], and the <Thought_Trail> above, determine your absolute next step natively.
If the <Mission> is fully complete, call 'complete_task'.

[IMPORTANT] When generating Python code, DO NOT use emoji characters (✅, ❌, 🎉, ✨, 🔥, 🚀, ✓, ✔, ✗, ✘) in print statements.
Use plain text like [SUCCESS], [ERROR], [DONE], [OK], [FAIL], [V], [X] instead.
"""

        try:
            if not silent:
                update_agent_status(
                    step=step + 1,
                    total_steps=max_steps,
                    thought="Thinking...",
                    action="THINKING",
                    action_detail="",
                    tokens=total_loop_tokens,
                )

            ai_response = {}
            max_api_retries = 10
            provider_switched = False
            for attempt in range(max_api_retries):
                try:
                    panic_step = max_steps - 2
                    full_prompt = (
                        AGENT_SYSTEM_PROMPT.format(
                            max_steps=max_steps, panic_step=panic_step
                        )
                        + "\n\n"
                        + prompt
                    )

                    if pending_image_payloads:
                        content_block = [{"type": "text", "text": full_prompt}] + pending_image_payloads
                        messages = [{"role": "user", "content": content_block}]
                        pending_image_payloads = []
                    else:
                        messages = [{"role": "user", "content": full_prompt}]

                    if any(name in current_provider.__class__.__name__.lower() for name in ["regolo", "openrouter", "custom"]):
                        thought_text = ""
                        content_text = ""
                        tool_calls = []
                        live_tokens = total_loop_tokens
                        chunk_counter = 0
                        for chunk in current_provider.generate_stream(
                            messages=messages,
                            tools=native_tools,
                            temperature=0.1,
                            max_tokens=4096,
                        ):
                            if chunk.get("error"):
                                raise Exception(chunk["error"])

                            rc = chunk.get("reasoning_content", "")
                            if rc:
                                thought_text += rc
                                live_tokens += count_tokens(rc)
                                chunk_counter += 1
                                if not silent and chunk_counter % 4 == 0:
                                    update_agent_status(
                                        step=step + 1,
                                        total_steps=max_steps,
                                        thought=thought_text.strip(),
                                        action="THINKING",
                                        action_detail="",
                                        tokens=live_tokens,
                                    )

                            ct = chunk.get("content", "")
                            if ct:
                                content_text += ct
                                live_tokens += count_tokens(ct)
                                chunk_counter += 1
                                if not silent and chunk_counter % 4 == 0:
                                    update_agent_status(
                                        step=step + 1,
                                        total_steps=max_steps,
                                        thought=thought_text.strip() or "Thinking...",
                                        action="THINKING",
                                        action_detail="",
                                        tokens=live_tokens,
                                    )

                            tc = chunk.get("tool_calls", [])
                            if tc:
                                tool_calls = tc
                                tc_str = str(tc)
                                live_tokens += max(1, len(tc_str) // 4)
                                chunk_counter += 1
                                if not silent and chunk_counter % 4 == 0:
                                    update_agent_status(
                                        step=step + 1,
                                        total_steps=max_steps,
                                        thought=thought_text.strip() or "Generating Tool Call...",
                                        action="THINKING",
                                        action_detail="",
                                        tokens=live_tokens,
                                    )

                        if not thought_text:
                            thought_text = content_text.strip() or "Analyzing context..."

                        output_tokens = (
                            count_tokens(thought_text)
                            + count_tokens(content_text)
                            + count_tokens(json.dumps(tool_calls))
                        )
                        total_loop_tokens += output_tokens

                        response = {
                            "content": content_text,
                            "reasoning_content": thought_text,
                            "tool_calls": tool_calls,
                            "error": None,
                        }
                    else:
                        response = current_provider.generate(
                            messages=messages,
                            tools=native_tools,
                            temperature=0.1,
                            max_tokens=4096,
                            stream=False,
                        )
                        if response.get("error"):
                            raise Exception(response["error"])

                        output_tokens = (
                            count_tokens(response.get("reasoning_content", ""))
                            + count_tokens(response.get("content", ""))
                            + count_tokens(json.dumps(response.get("tool_calls", [])))
                        )
                        total_loop_tokens += output_tokens

                    thought_text = response.get("reasoning_content") or response.get("content", "")
                    if thought_text is None:
                        thought_text = ""
                    thought_text = thought_text.strip() or "Analyzing context..."

                    tool_calls = response.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            func_name = tc["function"]["name"]
                            func_args = tc["function"]["arguments"]
                            if func_name == "complete_task":
                                ai_response["is_task_complete"] = True
                                ai_response["response"] = func_args.get(
                                    "response", "Task completed sir."
                                )
                            else:
                                ai_response[func_name] = func_args

                    ai_response["thought"] = thought_text

                    break

                except Exception as api_err:
                    error_msg = str(api_err)
                    is_quota_error = (
                        "429" in error_msg
                        or "RESOURCE_EXHAUSTED" in error_msg
                        or "quota" in error_msg.lower()
                    )

                    if is_quota_error and not provider_switched:
                        logger.warning(
                            f"⚠️ Provider {current_provider.__class__.__name__} hit quota/rate limit. Switching to fallback..."
                        )
                        try:
                            current_provider = fallback_provider
                            provider_switched = True
                            logger.info(
                                f"🔄 Switched to fallback provider: {AGENT_FALLBACK_PROVIDER}"
                            )
                            continue
                        except Exception as switch_err:
                            logger.error(
                                f"❌ Failed to switch to fallback: {switch_err}"
                            )
                            raise api_err

                    elif attempt < max_api_retries - 1:
                        logger.warning(
                            f"⚠️ API Generation failed (Attempt {attempt + 1}/{max_api_retries}): {api_err}. Retrying in 2 seconds..."
                        )
                        time.sleep(2)
                    else:
                        logger.error(
                            f"❌ API failed completely after {max_api_retries} attempts."
                        )
                        raise api_err

            logger.info(
                f"🧠 Agent Thought: {ai_response.get('thought', 'Thinking...')}"
            )

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
                                action_detail = (
                                    f"Recalling LTM: {value.get('lifetime_recall')}"
                                )
                        elif key == "search_actions" and isinstance(value, dict):
                            action_detail = (
                                value.get("web", "")
                                or value.get("youtube", "")
                                or value.get("arxiv", "")
                                or value.get("vault", "")
                                or value.get("read_webpage", "")
                            )
                        elif key == "execute_terminal_command" and isinstance(
                            value, dict
                        ):
                            action_detail = value.get("command", "")
                        elif key == "run_python_code" and isinstance(value, dict):
                            code = value.get("code_string", "").strip()
                            if code:
                                emoji_map = {
                                    "✅": "[OK]",
                                    "❌": "[ERR]",
                                    "🎉": "[DONE]",
                                    "✨": "[STAR]",
                                    "🔥": "[FIRE]",
                                    "🚀": "[ROCKET]",
                                    "✓": "[V]",
                                    "✔": "[V]",
                                    "✗": "[X]",
                                    "✘": "[X]",
                                    "\\u2705": "[OK]",
                                    "\\u274C": "[ERR]",
                                    "\\u2713": "[V]",
                                    "\\u2717": "[X]",
                                }
                                for emoji, text in emoji_map.items():
                                    code = code.replace(emoji, text)
                                ai_response["run_python_code"]["code_string"] = code
                            action_detail = (
                                code.split("\n")[0][:60] if code else "Running Script"
                            )
                        elif key == "deep_research" and isinstance(value, dict):
                            action_detail = value.get("topic", "")
                        elif key == "email_action" and isinstance(value, dict):
                            action_detail = f"To: {value.get('to', '')}"
                        elif key == "whatsapp_action" and isinstance(value, dict):
                            action_detail = f"To: {value.get('to', '')}"
                        elif key == "image_command" and isinstance(value, dict):
                            action_detail = value.get("prompt", "")
                        elif key == "calendar_action" and isinstance(value, dict):
                            action_detail = (
                                f"{value.get('action', '').capitalize()} Calendar"
                            )
                        elif key == "clipboard_action" and isinstance(value, dict):
                            action_detail = (
                                f"{value.get('action', '').upper()} Clipboard"
                            )
                        elif key == "vision" and isinstance(value, dict):
                            action_detail = value.get("query", "Inspecting media")
                        elif key == "file_operations" and isinstance(value, dict):
                            action_detail = value.get("action", "File operation")
                        elif key == "system_controller" and isinstance(value, dict):
                            if value.get("system_action") == "screenshot":
                                action_detail = "Capturing Screen..."
                            else:
                                action_detail = "Controlling System"
                        break

            if not silent:
                update_agent_status(
                    step=step + 1,
                    total_steps=max_steps,
                    thought=ai_response.get("thought", ""),
                    action=action_key,
                    action_detail=action_detail,
                    tokens=total_loop_tokens,
                )

            if ai_response.get("is_task_complete"):
                logger.info("✅ Agent declared task complete!")
                final_text = ai_response.pop("response", "Task completed sir.")

                sys_ctrl = ai_response.get("system_controller", {})
                if sys_ctrl.get("urls_to_open"):
                    ephemeral["last_found_links"] = sys_ctrl["urls_to_open"]
                if ai_response.get("image_command", {}).get("filename"):
                    ephemeral["last_generated_image"] = ai_response[
                        "image_command"
                    ]["filename"]

                update_agent_status(
                    step=0,
                    total_steps=max_steps,
                    thought="Task completed",
                    action="",
                    action_detail="",
                    tokens=total_loop_tokens,
                )

                launch_popup()
                update_typing_status("completed", final_text)

                return make_result(
                    final_text,
                    is_agentic=True,
                    agent_executed=True,
                    metadata=metadata_tracker,
                    **ai_response,
                )

            observation = None
            for attempt in range(retry_limit):
                try:
                    if action_key == "memory_actions":
                        mem_data = ai_response.get("memory_actions", {})

                        if mem_data.get("recent_logs"):
                            if memory_instance:
                                logger.info(
                                    "🧠 Agent requested full 15-day Chat History log natively."
                                )
                                history_data = (
                                    memory_instance.get_chat_history_for_tool()
                                )
                                observation = f"Observation: Successfully retrieved full 15-day history logs:\n\n{history_data}"
                            else:
                                observation = "Observation: Error -> Memory system instance is offline."

                        elif mem_data.get("lifetime_recall"):
                            query = mem_data.get("lifetime_recall")
                            logger.info(
                                f"🧠 Agent requesting LTM Recall for: {query}"
                            )
                            try:
                                from core.brain.Memory.LifetimeMemory import (
                                    ltm_engine,
                                )

                                observation = (
                                    ltm_engine.search_lifetime_memory(query)
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ LTM Recall tool crashed: {e}"
                                )
                                observation = (
                                    f"Observation: LTM Recall error -> {e}"
                                )
                        else:
                            observation = "Observation: No valid memory target provided. Use 'recent_logs' or 'lifetime_recall'."

                    elif action_key and action_key != "THINKING":
                        observation = execute_single_tool_sync(ai_response)

                    if observation:
                        if isinstance(observation, dict) and observation.get("type") == "image_payload":
                            for img in observation.get("data", []):
                                pending_image_payloads.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{img['mime_type']};base64,{img['data']}"}
                                })
                            observation = observation.get("observation", "Observation: [Media Loaded Inline] -> Images ready for inspection.")

                        obs_lower = str(observation).lower()
                        error_keywords = [
                            "[error]",
                            "traceback (most recent call last)",
                            "syntaxerror",
                            "pycompileerror",
                            "critical syntax error",
                            "failed to ",
                            "error ->",
                            "exception:",
                        ]
                        is_failure = any(kw in obs_lower for kw in error_keywords)

                        if not is_failure:
                            action_fingerprint = f"{action_key}:{str(ai_response.get(action_key, ''))[:100]}"
                            completed_actions.add(
                                f"{action_fingerprint} -> [SUCCESS]"
                            )
                            update_confirmed_facts(
                                confirmed_facts,
                                action_key,
                                action_detail,
                                observation,
                            )

                            if action_key in ["email_action", "whatsapp_action"]:
                                ephemeral["last_contact"] = ai_response.get(
                                    action_key, {}
                                ).get("to", "")

                            if "http" in observation and "link" in observation.lower():
                                urls = re.findall(r"https?://[^\s]+", observation)
                                if urls:
                                    ephemeral["last_found_links"] = urls[:3]
                            if (
                                "file" in observation.lower()
                                and (
                                    ".png" in observation
                                    or ".md" in observation
                                    or ".txt" in observation
                                    or ".jpg" in observation
                                )
                            ):
                                file_match = re.search(
                                    r"([\w\-:\\/.]+\.(png|md|txt|jpg))", observation
                                )
                                if file_match:
                                    ephemeral["last_accessed_file"] = (
                                        file_match.group(1)
                                    )

                            try:
                                if action_key == "system_controller":
                                    sys_data = ai_response.get(
                                        "system_controller", {}
                                    )
                                    if sys_data.get("apps_to_open"):
                                        metadata_tracker["apps_opened"].extend(
                                            sys_data["apps_to_open"]
                                        )
                                    if sys_data.get("apps_to_close"):
                                        metadata_tracker["apps_closed"].extend(
                                            sys_data["apps_to_close"]
                                        )
                                    if sys_data.get("urls_to_open"):
                                        metadata_tracker["system_events"].append(
                                            f"Opened URLs: {', '.join(sys_data['urls_to_open'])}"
                                        )
                                    if sys_data.get("system_action"):
                                        metadata_tracker["system_events"].append(
                                            f"System Action: {sys_data['system_action']}"
                                        )

                                    if (
                                        sys_data.get("system_action") == "screenshot"
                                        and sys_data.get("screenshot_filename")
                                    ):
                                        ephemeral["last_screenshot"] = (
                                            sys_data.get("screenshot_filename")
                                        )

                                elif action_key == "execute_terminal_command":
                                    cmd_data = ai_response.get(
                                        "execute_terminal_command", {}
                                    )
                                    metadata_tracker["system_events"].append(
                                        f"Terminal Command: {cmd_data.get('command', '')}"
                                    )

                                elif action_key == "run_python_code":
                                    metadata_tracker["system_events"].append(
                                        "Executed Python Code Script"
                                    )

                                else:
                                    metadata_tracker["system_events"].append(
                                        f"Executed {action_key}: {action_detail}"
                                    )

                            except Exception as meta_err:
                                logger.error(
                                    f"⚠️ Error tracking metadata: {meta_err}"
                                )

                            if not silent:
                                update_agent_status(
                                    step=step + 1,
                                    total_steps=max_steps,
                                    thought=ai_response.get("thought", ""),
                                    action=action_key,
                                    action_detail=action_detail,
                                    observation=str(observation)[:200],
                                    tokens=total_loop_tokens,
                                )
                            break
                        else:
                            logger.warning(
                                f"⚠️ Tool execution error detected: {str(observation)[:100]}. Sending to AI for self-correction..."
                            )
                            break
                    elif attempt < retry_limit - 1:
                        logger.warning(
                            f"⚠️ Tool attempt {attempt+1} failed: {observation}. Retrying in 2s..."
                        )
                        time.sleep(2)
                except Exception as tool_err:
                    observation = (
                        f"Observation: Tool execution error - {tool_err}"
                    )
                    break
            else:
                action_fingerprint = f"{action_key}:{str(ai_response.get(action_key, ''))[:100]}"
                completed_actions.add(
                    f"{action_fingerprint} -> [FAILED: After {retry_limit} retries]"
                )
                observation = f"Observation: Tool failed after {retry_limit} retries. Try a different approach."

            thought_str = ai_response.get("thought", "Thinking...")
            action_str = (
                f"{action_key} ({action_detail})"
                if action_key
                else "None (Missed Tool Call)"
            )
            optimized_obs = optimize_observation(observation, max_chars=10000)

            scratchpad += f"""
<Step number="{step+1}">
  <Thought>{thought_str}</Thought>
  <Executed_Tool>{action_str}</Executed_Tool>
  <Result>{optimized_obs}</Result>
</Step>
"""

            step += 1
            time.sleep(0.1)

        except Exception as e:
            error_msg = str(e)
            if (
                "429" in error_msg
                or "RESOURCE_EXHAUSTED" in error_msg
                or "quota" in error_msg.lower()
            ):
                logger.error("❌ All providers exhausted or rate limited!")
                if not silent:
                    update_agent_status(
                        step=0,
                        total_steps=max_steps,
                        thought="All providers failed",
                        action="",
                        action_detail="",
                        tokens=total_loop_tokens,
                    )
                    limit_msg = "Bhai, saare AI providers ki limit khatam ho gayi. Thoda ruko aur phir try karo."
                    launch_popup()
                    update_typing_status("completed", limit_msg)
                else:
                    limit_msg = "All providers exhausted."
                return make_result(
                    limit_msg, priority="high", agent_executed=True
                )

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

    if not silent:
        update_agent_status(
            step=0,
            total_steps=max_steps,
            thought="Max steps reached",
            action="",
            action_detail="",
            tokens=total_loop_tokens,
        )
        limit_msg = f"I have reached the maximum steps ({max_steps}). The task has hit the loop limit. Please provide a simpler command."
        launch_popup()
        update_typing_status("completed", limit_msg)
    else:
        limit_msg = f"Max steps ({max_steps}) reached."

    return make_result(
        limit_msg,
        priority="high",
        agent_executed=True,
        metadata=metadata_tracker,
    )