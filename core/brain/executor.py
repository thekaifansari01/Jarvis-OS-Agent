from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor
from core.logger.logger import logger
from tools.OpenCloseApps.open_any import open_any_app
from tools.OpenCloseApps.close_any import close_any_app
from tools.ImageGeneration.generate_image import handle_image_command
from tools.SearchTools.SearchHub import execute_search_actions
from tools.Messanger.email_manager import send_email, delete_email
from tools.Messanger.whatsapp.whatsapp import send_whatsapp_message, fetch_whatsapp_chats
from tools.Messanger.telegram import send_telegram_message, fetch_telegram_chats
from core.voice.tts import speak
from tools.SystemTools.clipboard_tool import read_clipboard, write_clipboard
from tools.SystemTools.SystemTools import SystemController
from tools.SystemTools.fileEditor import JarvisFileEditor
from tools.SearchTools.DeepResearch import deep_research_as_tool
from tools.Calendar.CalendarTool import create_event, check_events, delete_event
from tools.Terminal.terminalTool import execute_terminal_command, run_python_code
import shutil
import platform
import subprocess
import json
import os
import webbrowser
import pywhatkit
import traceback
import tempfile
import time

file_editor = JarvisFileEditor()

def execute_actions(result: Dict[str, any], executor: ThreadPoolExecutor) -> str:
    def log_action(message: str) -> None:
        logger.info(message)

    try:
        response_text = result.get('response', '')
        if response_text:
            log_action(f"🤖 JARVIS: {response_text}")
            executor.submit(speak, response_text)

        if result.get("agent_executed"):
            logger.debug("🤖 Agent tool execution complete. Skipping duplicate async execution.")
            return ""

        youtube_query = result.get('youtube_play')
        if youtube_query:
            def play_on_youtube(query):
                log_action(f"▶️ Playing on YouTube: {query}")
                try:
                    pywhatkit.playonyt(query)
                except Exception as e:
                    logger.error(f"❌ Failed to play on YouTube. Error: {e}\n{traceback.format_exc()}")
                    executor.submit(speak, "Sorry sir, YouTube par play karne mein error aa gaya.")
            executor.submit(play_on_youtube, youtube_query)

        if result.get('apps_to_open'):
            def thread_open(apps):
                try:
                    opened = open_any_app(apps)
                    if opened:
                        log_action(f"✅ Opened Apps: {', '.join(opened)}")
                    else:
                        logger.warning(f"⚠️ Failed to open some/all apps: {', '.join(apps)}")
                except Exception as e:
                    logger.error(f"❌ App opening failed: {e}\n{traceback.format_exc()}")
            executor.submit(thread_open, result['apps_to_open'])

        if result.get('apps_to_close'):
            def thread_close(apps):
                try:
                    closed = close_any_app(apps)
                    if closed:
                        log_action(f"✅ Closed Apps: {', '.join(closed)}")
                    else:
                        logger.warning(f"⚠️ Failed to close some/all apps: {', '.join(apps)}")
                except Exception as e:
                    logger.error(f"❌ App closing failed: {e}\n{traceback.format_exc()}")
            executor.submit(thread_close, result['apps_to_close'])

        if result.get('urls_to_open'):
            def thread_open_urls(urls):
                for url in urls:
                    if url.startswith('http'):
                        log_action(f"🔗 Opening Dynamic Link: {url}")
                        try:
                            webbrowser.open(url)
                        except Exception as e:
                            logger.error(f"❌ Failed to open link {url}. Error: {e}")
            executor.submit(thread_open_urls, result['urls_to_open'])

        if result.get('volume'):
            def change_vol():
                vol_data = result['volume']
                action = vol_data.get('action')
                val = vol_data.get('value', 10)
                relative = action in ['increase', 'decrease']
                if action == 'decrease': val = -abs(val)
                msg = SystemController.change_volume(val, relative)
                log_action(f"🔊 {msg}")
            executor.submit(change_vol)

        if result.get('brightness'):
            def change_bright():
                br_data = result['brightness']
                action = br_data.get('action')
                val = br_data.get('value', 10)
                relative = action in ['increase', 'decrease']
                if action == 'decrease': val = -abs(val)
                msg = SystemController.change_brightness(val, relative)
                log_action(f"☀️ {msg}")
            executor.submit(change_bright)

        if result.get('system_action'):
            def sys_act():
                action = result['system_action']
                if action == 'screenshot':
                    temp_dir = tempfile.gettempdir()
                    msg = SystemController.capture_screenshot(save_dir=temp_dir)
                    log_action(f"📸 {msg}")
                    executor.submit(speak, "Screenshot save ho gaya sir.")
                elif action in ['lock', 'sleep']:
                    time.sleep(0.8)
                    if action == 'lock':
                        SystemController.lock_pc()
                        log_action("🔒 PC Locked")
                    elif action == 'sleep':
                        SystemController.sleep_pc()
                        log_action("🌙 PC Sleep")
            executor.submit(sys_act)
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in execute_actions (Fast Brain): {e}\n{traceback.format_exc()}")

    return ""

def _safe_int(val, default=None):
    if val is None:
        return default
    try:
        return max(1, int(val))
    except (ValueError, TypeError):
        return default

def execute_file_operation(action_dict: dict) -> str:
    try:
        action = action_dict.get("action")
        
        if action == "repo_map":
            file_path = action_dict.get("file_path", None)
            result = file_editor.get_repo_map(file_path=file_path)
            return f"Observation: {result}"

        if action == "view":
            file_path = action_dict.get("file_path")
            file_paths = action_dict.get("file_paths")
            if not file_path and not file_paths:
                return "Observation: [ERROR] Either 'file_path' or 'file_paths' must be provided for view."
            
            if file_path:
                file_path = os.path.abspath(file_path.replace("\\", "/"))
            if file_paths:
                file_paths = [os.path.abspath(p.replace("\\", "/")) for p in file_paths if p]
            
            start = _safe_int(action_dict.get("start_line"))
            end = _safe_int(action_dict.get("end_line"))
            result = file_editor.view(file_path=file_path, file_paths=file_paths, start_line=start, end_line=end)
            return f"Observation: {result}"

        if action == "replace_block":
            file_path = action_dict.get("file_path")
            if not file_path:
                return "Observation: [ERROR] Missing 'file_path' for replace_block."
            file_path = os.path.abspath(file_path.replace("\\", "/"))
            search_block = action_dict.get("search_block")
            replace_block = action_dict.get("replace_block")
            if not search_block or replace_block is None:
                return "Observation: [ERROR] Missing 'search_block' or 'replace_block' for replace_block action."
            result = file_editor.replace_block(file_path, str(search_block), str(replace_block))
            return f"Observation: {result}"

        if action == "create":
            file_path = action_dict.get("file_path")
            content = action_dict.get("content", "")
            files = action_dict.get("files")
            if not file_path and not files:
                return "Observation: [ERROR] Either 'file_path' or 'files' must be provided for create."
            
            if file_path:
                file_path = os.path.abspath(file_path.replace("\\", "/"))
            if files:
                for item in files:
                    if "file_path" in item:
                        item["file_path"] = os.path.abspath(item["file_path"].replace("\\", "/"))
            
            result = file_editor.create(file_path=file_path, content=content, files=files)
            return f"Observation: {result}"

        else:
            return f"Observation: [ERROR] Unknown file action '{action}'. Supported: repo_map, view, replace_block, create."
            
    except Exception as e:
        return f"Observation: [ERROR] File operation runtime crash: {str(e)}"
    
def execute_single_tool_sync(action_dict: Dict[str, any]) -> str:
    observation = "Observation: No valid action executed."

    search_actions = action_dict.get('search_actions')
    if search_actions and isinstance(search_actions, dict) and any(search_actions.values()):
        try:
            logger.info(f"🤖 Agent executing Search: {list(search_actions.keys())}")

            if search_actions.get('vault'):
                try:
                    from core.brain.RagEngine import rag_engine
                    vault_query = search_actions.get('vault')
                    results = rag_engine.search_vault(vault_query)

                    if results:
                        observation_parts = []
                        for hit in results:
                            status = "✅ COMPLETE FILE" if hit['is_complete'] else "⚠️ PARTIAL FILE"
                            file_size_kb = f"{hit['file_size_bytes'] / 1024:.1f} KB" if hit['file_size_bytes'] > 0 else "Unknown"

                            obs = f"""
            📁 FILE: {hit['file_name']}
            📂 PATH: {hit['file_path']}
            📊 SIZE: {file_size_kb} ({hit['file_size_bytes']} bytes)
            📑 CHUNKS: {hit['chunks_found']} of {hit['total_chunks']}
            ✅ STATUS: {status}

            CONTENT:
            {hit['content']}

            {'✅ This is the complete file content. Use this directly. No need to read separately.' if hit['is_complete'] else '⚠️ Only partial content shown. Use file_operations to read full file if needed.'}
            """
                            observation_parts.append(obs)

                        return "Observation: Vault Search Results:\n\n" + "\n" + "="*50 + "\n".join(observation_parts)
                    else:
                        return "Observation: Vault Search found no matching documents."

                except Exception as e:
                    logger.error(f"❌ RAG/Vault Search error: {e}\n{traceback.format_exc()}")
                    return f"Observation: Vault Search failed internally due to {e}."

            search_output = execute_search_actions(search_actions)

            if search_output:
                return f"Observation: Search successful. Fetched Data -> {search_output[:15000]}..."

            return "Observation: Search completed but NO data found. 💡 Tip: Try different keywords or a broader search."
        except Exception as e:
            logger.error(f"❌ Search Hub API failed: {e}\n{traceback.format_exc()}")
            return f"Observation: Search API failed -> {e}"

    terminal_cmd = action_dict.get('execute_terminal_command')
    if terminal_cmd and isinstance(terminal_cmd, dict) and terminal_cmd.get('command'):
        try:
            logger.info(f"🤖 Agent executing Terminal Command: {terminal_cmd.get('command')}")
            return execute_terminal_command(terminal_cmd.get('command'))
        except Exception as e:
            logger.error(f"❌ Terminal Command failed: {e}\n{traceback.format_exc()}")
            return f"Observation: Terminal Command error -> {e}"

    python_cmd = action_dict.get('run_python_code')
    if python_cmd and isinstance(python_cmd, dict) and python_cmd.get('code_string'):
        try:
            logger.info(f"🤖 Agent executing Python Script.")
            return run_python_code(python_cmd.get('code_string'))
        except Exception as e:
            logger.error(f"❌ Python Execution failed: {e}\n{traceback.format_exc()}")
            return f"Observation: Python Execution error -> {e}"


    email_action = action_dict.get('email_action', {})
    if email_action and isinstance(email_action, dict) and email_action.get('to'):
        try:
            raw_requested_to = email_action.get('to', '').strip()
            requested_to_lower = raw_requested_to.lower()

            subject = email_action.get('subject', 'Update')
            body = email_action.get('body', '')
            file_path_raw = email_action.get('file_path', '')

            contact_book = {}
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            contact_file_path = os.path.join(base_dir, "tools", "Messanger", "contact_book.json")

            try:
                if os.path.exists(contact_file_path):
                    with open(contact_file_path, "r", encoding="utf-8") as f:
                        raw_contacts = json.load(f)
                        contact_book = {k.lower(): v for k, v in raw_contacts.items()}
            except Exception as e:
                logger.warning(f"⚠️ Contact book load error: {e}")

            if "@" in raw_requested_to:
                to_address = raw_requested_to
            else:
                to_address = contact_book.get(requested_to_lower, raw_requested_to)

            if "@" not in to_address:
                logger.warning(f"⚠️ Attempted email to invalid address/name: {to_address}")
                return f"Observation: Error -> '{raw_requested_to}' contact book mein nahi mila ya valid email nahi hai. User se bolo ki unka exact email address batayein."

            attachment_abs_path = None
            if file_path_raw:
                if os.path.exists(file_path_raw):
                    attachment_abs_path = file_path_raw
                else:
                    logger.warning(f"⚠️ Email attachment not found: {file_path_raw}")
                    return f"Observation: Failed to send email. Attachment '{file_path_raw}' not found at the given absolute path."

            logger.info(f"🤖 Agent Sending Email to: {to_address}")

            success = send_email(to_address, subject, body, attachment_abs_path)

            if success:
                logger.info(f"✅ Email successfully sent to {to_address}")
                return f"Observation: Email successfully sent to {to_address}."
            else:
                logger.error(f"❌ send_email returned False for {to_address}. Check SMTP configurations.")
                return f"Observation: Failed to send email to {to_address}. Please verify SMTP credentials and internet connection."

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR in Email Action: {e}\n{traceback.format_exc()}")
            return f"Observation: Critical error while preparing or sending email -> {e}"

    whatsapp_action = action_dict.get('whatsapp_action', {})
    if whatsapp_action and isinstance(whatsapp_action, dict) and whatsapp_action.get('to'):
        try:
            action_type = whatsapp_action.get('action', 'send')
            to_name = whatsapp_action.get('to')

            if action_type == 'fetch':
                start_date = whatsapp_action.get('start_date')
                end_date = whatsapp_action.get('end_date')
                if not start_date or not end_date:
                    return "Observation: Error -> 'start_date' and 'end_date' are required for fetching chats."

                logger.info(f"🤖 Agent Fetching WhatsApp chat for: {to_name} from {start_date} to {end_date}")
                wa_result = fetch_whatsapp_chats(to_name, start_date, end_date)
                return f"Observation: {wa_result}"

            else:
                msg_body = whatsapp_action.get('message', '')
                file_path_raw = whatsapp_action.get('file_path', '')

                attachment_abs_path = None
                if file_path_raw:
                    if os.path.exists(file_path_raw):
                        attachment_abs_path = file_path_raw
                    else:
                        logger.warning(f"⚠️ WhatsApp attachment not found: {file_path_raw}")
                        return f"Observation: Failed to send WhatsApp. Attachment '{file_path_raw}' not found at the given absolute path."

                logger.info(f"🤖 Agent Sending WhatsApp to: {to_name}")
                wa_result = send_whatsapp_message(to_name, msg_body, attachment_abs_path)

                if "Error" in wa_result or "failed" in wa_result.lower():
                    logger.error(f"❌ WhatsApp message failed: {wa_result}")
                else:
                    logger.info(f"✅ WhatsApp result: {wa_result}")

                return f"Observation: {wa_result}"
        except Exception as e:
            logger.error(f"❌ ERROR in WhatsApp action: {e}\n{traceback.format_exc()}")
            return f"Observation: WhatsApp action crashed -> {e}"

    telegram_action = action_dict.get('telegram_action', {})
    if telegram_action and isinstance(telegram_action, dict) and telegram_action.get('to'):
        try:
            action_type = telegram_action.get('action', 'send')
            to_name = telegram_action.get('to')

            if action_type == 'fetch':
                start_date = telegram_action.get('start_date')
                end_date = telegram_action.get('end_date')
                if not start_date or not end_date:
                    return "Observation: Error -> 'start_date' and 'end_date' are required for fetching chats."

                logger.info(f"🤖 Agent Fetching Telegram chat for: {to_name} from {start_date} to {end_date}")
                tg_result = fetch_telegram_chats(to_name, start_date, end_date)
                return f"Observation: {tg_result}"

            else:
                msg_body = telegram_action.get('message', '')
                file_paths = telegram_action.get('file_paths', [])

                logger.info(f"🤖 Agent Sending Telegram to: {to_name}")
                tg_result = send_telegram_message(to_name, msg_body, file_paths)

                if "Error" in tg_result or "failed" in tg_result.lower():
                    logger.error(f"❌ Telegram message failed: {tg_result}")
                else:
                    logger.info(f"✅ Telegram result: {tg_result}")

                return f"Observation: {tg_result}"
        except Exception as e:
            logger.error(f"❌ ERROR in Telegram action: {e}\n{traceback.format_exc()}")
            return f"Observation: Telegram action crashed -> {e}"

    system_ctrl = action_dict.get('system_controller', {})
    if system_ctrl and isinstance(system_ctrl, dict):
        sys_observations = []

        apps_to_open = system_ctrl.get('apps_to_open')
        if apps_to_open and isinstance(apps_to_open, list) and apps_to_open:
            try:
                opened = open_any_app(apps_to_open)
                if opened:
                    sys_observations.append(f"Opened Apps: {', '.join(opened)}")
                    logger.info(f"✅ System Controller opened apps: {opened}")
                else:
                    sys_observations.append(f"Failed to open apps: {', '.join(apps_to_open)}")
                    logger.warning(f"⚠️ System Controller failed to open apps: {apps_to_open}")
            except Exception as e:
                logger.error(f"❌ App open error: {e}")
                sys_observations.append(f"App open error: {e}")

        apps_to_close = system_ctrl.get('apps_to_close')
        if apps_to_close and isinstance(apps_to_close, list) and apps_to_close:
            try:
                closed = close_any_app(apps_to_close)
                if closed:
                    sys_observations.append(f"Closed Apps: {', '.join(closed)}")
                    logger.info(f"✅ System Controller closed apps: {closed}")
                else:
                    sys_observations.append(f"Failed to close apps: {', '.join(apps_to_close)}")
                    logger.warning(f"⚠️ System Controller failed to close apps: {apps_to_close}")
            except Exception as e:
                logger.error(f"❌ App close error: {e}")
                sys_observations.append(f"App close error: {e}")

        urls_to_open = system_ctrl.get('urls_to_open')
        if urls_to_open and isinstance(urls_to_open, list) and urls_to_open:
            try:
                for url in urls_to_open:
                    if url.startswith('http'): webbrowser.open(url)
                sys_observations.append(f"Opened URLs: {', '.join(urls_to_open)}")
                logger.info(f"✅ System Controller opened URLs: {urls_to_open}")
            except Exception as e:
                logger.error(f"❌ URL open error: {e}")
                sys_observations.append(f"URL open error: {e}")

        youtube_query = system_ctrl.get('youtube_play')
        if youtube_query and isinstance(youtube_query, str) and youtube_query.strip():
            try:
                logger.info(f"🤖 Agent playing YouTube: {youtube_query}")
                pywhatkit.playonyt(youtube_query)
                sys_observations.append(f"Playing on YouTube: '{youtube_query}'")
            except Exception as e:
                logger.error(f"❌ YouTube playback error: {e}")
                sys_observations.append(f"YouTube error: {e}")

        vol_action = system_ctrl.get('volume_action') or system_ctrl.get('volume', {}).get('action')
        vol_val = system_ctrl.get('volume_value') or system_ctrl.get('volume', {}).get('value', 10)
        if vol_action:
            try:
                relative = vol_action in ['increase', 'decrease']
                if vol_action == 'decrease':
                    vol_val = -abs(int(vol_val))
                msg = SystemController.change_volume(int(vol_val), relative)
                sys_observations.append(msg)
                logger.info(f"✅ System Controller Volume: {msg}")
            except Exception as e:
                logger.error(f"❌ Volume change error: {e}")
                sys_observations.append(f"Volume error: {e}")

        br_action = system_ctrl.get('brightness_action') or system_ctrl.get('brightness', {}).get('action')
        br_val = system_ctrl.get('brightness_value') or system_ctrl.get('brightness', {}).get('value', 10)
        if br_action:
            try:
                relative = br_action in ['increase', 'decrease']
                if br_action == 'decrease':
                    br_val = -abs(int(br_val))
                msg = SystemController.change_brightness(int(br_val), relative)
                sys_observations.append(msg)
                logger.info(f"✅ System Controller Brightness: {msg}")
            except Exception as e:
                logger.error(f"❌ Brightness change error: {e}")
                sys_observations.append(f"Brightness error: {e}")

        system_action = system_ctrl.get('system_action')
        if system_action:
            if system_action == 'screenshot':
                custom_filename = system_ctrl.get('screenshot_filename')
                temp_dir = tempfile.gettempdir()

                msg = SystemController.capture_screenshot(filename=custom_filename, save_dir=temp_dir)

                if "error" in msg.lower():
                    sys_observations.append(msg)
                else:
                    sys_observations.append(f"{msg}. Screenshot taken successfully.")

            elif system_action == 'lock':
                sys_observations.append(SystemController.lock_pc())
            elif system_action == 'sleep':
                sys_observations.append(SystemController.sleep_pc())

        if sys_observations:
            return f"Observation: System Actions Completed -> " + " | ".join(sys_observations)
        else:
            return "Observation: System controller called but no valid parameters provided."

    image_cmd = action_dict.get('image_command')
    if image_cmd and isinstance(image_cmd, dict) and image_cmd.get('action'):
        try:
            action = image_cmd.get('action', 'generate')
            prompt = image_cmd.get('prompt', '')
            filename = image_cmd.get('filename', 'agent_image')
            target_file = image_cmd.get('target_file')

            if not prompt:
                return "Observation: Image action missing prompt."

            logger.info(f"🤖 Agent executing image {action}: {prompt}")
            result_path = handle_image_command(action, prompt, filename, target_file)

            if result_path:
                logger.info(f"✅ Image {action} successful: {result_path}")
                return f"Observation: Image successfully {action}d at absolute path: {result_path}."
            else:
                logger.error(f"❌ Image {action} failed. returned None.")
                return f"Observation: Image {action} failed. API might be down or rejected the prompt."
        except Exception as e:
            logger.error(f"❌ ERROR in Image Generation/Editing: {e}\n{traceback.format_exc()}")
            return f"Observation: Image error -> {e}"

    deep_research_cmd = action_dict.get('deep_research')
    if deep_research_cmd and isinstance(deep_research_cmd, dict):
        topic = deep_research_cmd.get('topic', '')
        if not topic: return "Observation: Deep research called without 'topic' parameter."
        logger.info(f"🤖 Agent initiating Deep Research on: {topic}")
        try:
            result = deep_research_as_tool(topic)
            logger.info(f"✅ Deep Research completed for: {topic}")
            return f"Observation: {result}"
        except Exception as e:
            logger.error(f"❌ Deep Research crashed: {e}\n{traceback.format_exc()}")
            return f"Observation: Deep research error: {e}"

    calendar_cmd = action_dict.get('calendar_action')
    if calendar_cmd and isinstance(calendar_cmd, dict) and calendar_cmd.get('action'):
        try:
            action = calendar_cmd.get('action')
            logger.info(f"🤖 Agent executing Calendar Action: {action}")

            if action == 'create':
                summary = calendar_cmd.get('summary', 'Reminder')
                start = calendar_cmd.get('start_time')
                end = calendar_cmd.get('end_time')
                desc = calendar_cmd.get('description', '')
                if not start or not end:
                    return "Observation: Error -> 'create' action requires start_time and end_time."
                return create_event(summary, start, end, desc)

            elif action == 'check':
                start = calendar_cmd.get('start_time')
                end = calendar_cmd.get('end_time')
                return check_events(start, end)

            elif action == 'delete':
                event_id = calendar_cmd.get('event_id')
                summary_query = calendar_cmd.get('summary_query')
                return delete_event(event_id, summary_query)

            else:
                return f"Observation: Unknown calendar action '{action}'."
        except Exception as e:
            logger.error(f"❌ Calendar tool crashed: {e}\n{traceback.format_exc()}")
            return f"Observation: Calendar tool error -> {e}"

    file_ops = action_dict.get('file_operations')
    if file_ops and isinstance(file_ops, dict):
        logger.info("🤖 Agent executing File Operation")
        return execute_file_operation(file_ops)

    clipboard_cmd = action_dict.get('clipboard_action')
    if clipboard_cmd and isinstance(clipboard_cmd, dict) and clipboard_cmd.get('action'):
        try:
            action_type = clipboard_cmd.get('action')
            if action_type == 'read':
                logger.info("🤖 Agent executing Clipboard: READ")
                content = read_clipboard()
                if content:
                    return f"Observation: Clipboard currently contains this text -> {content}"
                else:
                    return "Observation: Clipboard is empty right now."
            elif action_type == 'write':
                content_to_write = clipboard_cmd.get('content', '')
                if not content_to_write:
                    return "Observation: Missing 'content' to write to clipboard."
                logger.info("🤖 Agent executing Clipboard: WRITE")
                success = write_clipboard(content_to_write)
                if success:
                    return f"Observation: Successfully copied text to clipboard. (Length: {len(content_to_write)} characters)."
                else:
                    logger.error("❌ Failed to write to clipboard via OS.")
                    return "Observation: Failed to write text to OS clipboard."
        except Exception as e:
            logger.error(f"❌ Clipboard tool crashed: {e}\n{traceback.format_exc()}")
            return f"Observation: Clipboard tool error -> {e}"

    return observation