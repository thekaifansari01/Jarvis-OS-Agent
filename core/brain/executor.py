from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor
from core.logger.logger import logger
from tools.OpenCloseApps.open_any import open_any_app
from tools.OpenCloseApps.close_any import close_any_app
from tools.ImageGeneration.generate_image import handle_image_command 
from tools.SearchTools.SearchHub import execute_search_actions
from tools.Messanger.email_manager import send_email, delete_email
from tools.Messanger.whatsapp.whatsapp import send_whatsapp_message, fetch_whatsapp_chats
from core.voice.tts import speak
from tools.workspace.workspace import workspace
from tools.SystemTools.clipboard_tool import read_clipboard, write_clipboard
from tools.SystemTools.SystemTools import SystemController
from tools.SearchTools.DeepResearch import deep_research_as_tool
from tools.Calendar.CalendarTool import create_event, check_events, delete_event
import shutil
import platform
import subprocess
import json
import os
import webbrowser
import pywhatkit
import difflib
import traceback

def smart_file_finder(requested_name):
    """Voice commands ke liye Fuzzy/Smart File Matching - uses registry.json for O(1) lookup"""
    try:
        if not requested_name:
            return None

        exact_match = workspace.find_file_in_workspace(requested_name)
        if exact_match:
            return exact_match

        registry = workspace._load_registry()
        files_list = registry.get("files", [])
        if not files_list:
            return None

        folder_paths = {
            "Creations": workspace.creations_dir,
            "Vault": workspace.vault_dir,
            "Temp": workspace.temp_dir
        }

        clean_map = {}
        for entry in files_list:
            filename = entry.get("filename")
            location = entry.get("location", "/Vault").strip("/") 
            folder_name = location.split("/")[0] if location else "Vault"
            folder_path = folder_paths.get(folder_name, workspace.vault_dir)
            full_path = folder_path / filename

            if not full_path.exists():
                continue

            clean_name = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
            clean_map[clean_name] = full_path

        if not clean_map:
            return None

        req_clean = requested_name.lower().replace(" file", "").replace(" wali", "").replace(" report", "").replace(".md", "").replace(".txt", "").strip()

        if req_clean in clean_map:
            return clean_map[req_clean]

        matches = difflib.get_close_matches(req_clean, clean_map.keys(), n=1, cutoff=0.4)
        if matches:
            matched_path = clean_map[matches[0]]
            logger.info(f"🔍 Smart Finder: '{requested_name}' matched with '{matched_path.name}'")
            return matched_path

        return None
    except Exception as e:
        logger.error(f"❌ Error in smart_file_finder: {e}")
        return None

def execute_actions(result: Dict[str, any], executor: ThreadPoolExecutor) -> str:
    """Fast Brain execution: Only handles Chat, Apps, URLs, YouTube, Workspace Open."""
    
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
                if action == 'lock':
                    SystemController.lock_pc()
                    log_action("🔒 PC Locked")
                elif action == 'sleep':
                    SystemController.sleep_pc()
                    log_action("🌙 PC Sleep")
                elif action == 'screenshot':
                    from tools.workspace.workspace import workspace
                    msg = SystemController.capture_screenshot(save_dir=str(workspace.vault_dir))
                    log_action(f"📸 {msg}")
                    executor.submit(speak, "Screenshot vault mein save ho gaya sir.")
            executor.submit(sys_act)

        workspace_file_to_open = result.get('workspace_file_to_open')
        if workspace_file_to_open and isinstance(workspace_file_to_open, str) and workspace_file_to_open.strip():
            def open_workspace_file_fast(filename):
                file_path = smart_file_finder(filename)
                if file_path:
                    log_action(f"📂 Fast Brain: Opening workspace file: {file_path.name}")
                    try:
                        if platform.system() == 'Windows':
                            os.startfile(str(file_path))
                        elif platform.system() == 'Darwin':
                            subprocess.call(('open', str(file_path)))
                        else:
                            subprocess.call(('xdg-open', str(file_path)))
                        executor.submit(speak, f"Sir, {file_path.name} khol diya.")
                    except Exception as e:
                        logger.error(f"❌ OS Failed to open file {file_path.name}. Error: {e}\n{traceback.format_exc()}")
                        executor.submit(speak, f"Sir, file system error ki wajah se file nahi khul rahi.")
                else:
                    logger.warning(f"❌ Workspace file not found for opening: {filename}")
                    executor.submit(speak, f"Sir, '{filename}' workspace mein nahi mili.")
            executor.submit(open_workspace_file_fast, workspace_file_to_open.strip())
            
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in execute_actions (Fast Brain): {e}\n{traceback.format_exc()}")
        
    return ""


def execute_single_tool_sync(action_dict: Dict[str, any]) -> str:
    """Executes a single tool synchronously and returns the Observation string."""
    observation = "Observation: No valid action executed."

    search_actions = action_dict.get('search_actions')
    if search_actions and isinstance(search_actions, dict) and any(search_actions.values()):
        try:
            logger.info(f"🤖 Agent executing Search: {list(search_actions.keys())}")
            
            if search_actions.get('vault'):
                try:
                    from core.brain.RagEngine import rag_engine
                    vault_query = search_actions.get('vault')
                    rag_hits = rag_engine.search_vault(vault_query)
                    if rag_hits:
                        vault_data = "\n\n".join([f"📄 [File: {hit['file_path']}]\nSnippet: {hit['content']}" for hit in rag_hits])
                        return f"Observation: Vault Search successful. Found these snippets:\n{vault_data}\n💡 Hint: If you need to read the FULL file, use 'workspace_action' -> 'read' with the File name."
                    return "Observation: Vault Search found no matching documents."
                except Exception as e:
                    logger.error(f"❌ RAG/Vault Search error: {e}\n{traceback.format_exc()}")
                    return f"Observation: Vault Search failed internally due to {e}."

            from tools.SearchTools.SearchHub import execute_search_actions
            search_output = execute_search_actions(search_actions)
            
            if search_output:
                return f"Observation: Search successful. Fetched Data -> {search_output[:15000]}..."
                
            return "Observation: Search completed but NO data found. 💡 Tip: Try different keywords or a broader search."
        except Exception as e:
            logger.error(f"❌ Search Hub API failed: {e}\n{traceback.format_exc()}")
            return f"Observation: Search API failed -> {e}"

    workspace_cmd = action_dict.get('workspace_action')
    if workspace_cmd and isinstance(workspace_cmd, dict) and workspace_cmd.get('action'):
        act = workspace_cmd.get('action')
        fname = workspace_cmd.get('file', '').strip("/\\")
        
        if act == "list":
            try:
                context_str = workspace.get_workspace_context()
                return f"Observation: Workspace files:\n{context_str}"
            except Exception as e:
                logger.error(f"❌ Workspace list failed: {e}\n{traceback.format_exc()}")
                return f"Observation: Workspace list failed -> {e}"
        
        if not fname:
            return "Observation: Error -> Workspace action requires 'file' parameter."
            
        if act == "write":
            if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                return f"Observation: Error -> You cannot write or create image files using workspace_action. Use the 'image_command' tool instead."
            try:
                logger.info(f"🤖 Agent Creating/Writing File: {fname}")
                content = workspace_cmd.get('content', '')
                if not content:
                    return f"Observation: Error -> Missing 'content' parameter to write into '{fname}'."
                
                clean_fname = os.path.basename(fname.replace("\\", "/"))
                
                existing_file_path = smart_file_finder(clean_fname)
                
                if existing_file_path:
                    file_path = existing_file_path
                    folder_name = file_path.parent.name
                    logger.info(f"✏️ Overwriting/Editing existing file at: {file_path}")
                else:
                    target_dir = workspace.creations_dir
                    file_path = target_dir / clean_fname
                    folder_name = "Creations"
                    logger.info(f"🆕 Creating new file at: {file_path}")
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                
                workspace.add_file_record(file_path.name, folder_name, "Generated/Edited and saved by AI Agent.")
                workspace.sync_registry()
                return f"Observation: Successfully wrote to '{file_path.name}' in {folder_name} folder. [Length: {len(content)} chars]"
            except PermissionError:
                logger.error(f"❌ Permission denied while writing {fname}")
                return f"Observation: Error -> OS Permission denied. Cannot write to '{fname}'."
            except Exception as e:
                logger.error(f"❌ Workspace file write failed: {e}\n{traceback.format_exc()}")
                return f"Observation: Workspace file write failed -> {e}"
        
        file_path = smart_file_finder(fname)
        if not file_path:
            for folder in [workspace.creations_dir, workspace.vault_dir, workspace.temp_dir]:
                candidate = folder / fname
                if candidate.exists():
                    file_path = candidate
                    break
            if not file_path:
                return f"Observation: File '{fname}' NOT FOUND. 💡 Tip: Try using {{\"workspace_action\": {{\"action\": \"list\"}}}} to see exact available filenames."

        try:
            if act == "read":
                logger.info(f"🤖 Agent Reading File: {file_path.name}")
                if file_path.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    return f"Observation: Workspace Image loaded successfully at {file_path}. Please analyze this image in the next step."
                elif file_path.name.lower().endswith(('.pdf', '.exe', '.zip', '.mp4', '.mp3')):
                    return f"Observation: Error -> Cannot read binary file '{file_path.name}'. Do not try to read this again."
                
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                max_read_chars = 150000
                if len(content) > max_read_chars:
                    logger.warning(f"⚠️ File {file_path.name} is too large. Truncating for Agent memory.")
                    content = content[:max_read_chars] + f"\n\n... [⚠️ TRUNCATED: Original file had {len(content)} characters. Displaying first {max_read_chars} chars to save Context Window.]"
                
                return f"Observation: Content of {file_path.name} fetched. [Length: {len(content)} chars] -> {content}"
            
            elif act == "open":
                logger.info(f"🤖 Agent Opening File: {file_path.name}")
                if platform.system() == 'Windows': os.startfile(str(file_path))
                elif platform.system() == 'Darwin': subprocess.call(('open', str(file_path)))
                else: subprocess.call(('xdg-open', str(file_path)))
                return f"Observation: Successfully opened file '{file_path.name}' on screen."
            
            elif act == "delete":
                logger.info(f"🤖 Agent Deleting File: {file_path.name}")
                os.remove(file_path)
                workspace.sync_registry()
                return f"Observation: Successfully deleted file '{file_path.name}'."
            
            elif act == "move":
                dest_folder = workspace_cmd.get('to', 'Vault').capitalize()
                if dest_folder not in ["Vault", "Creations", "Temp"]: dest_folder = "Vault"
                dest_dir = getattr(workspace, f"{dest_folder.lower()}_dir", workspace.vault_dir)
                dest_name = workspace_cmd.get('dest_name', file_path.name)
                dest_path = dest_dir / dest_name
                
                if dest_path.exists():
                    return f"Observation: Move FAILED. File '{dest_name}' already exists in {dest_folder}. Please use a different dest_name or delete the existing file first."
                
                shutil.move(str(file_path), str(dest_path))
                workspace.add_file_record(dest_name, dest_folder, f"Moved by Agent from {file_path.parent.name}")
                workspace.sync_registry()
                return f"Observation: Successfully moved '{file_path.name}' to {dest_folder} as '{dest_name}'."
            else:
                return f"Observation: Workspace action '{act}' not supported."
        except Exception as e:
            logger.error(f"❌ Workspace action '{act}' failed on {fname}: {e}\n{traceback.format_exc()}")
            return f"Observation: Workspace action failed -> {e}"

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
                found = smart_file_finder(file_path_raw)
                if found: 
                    attachment_abs_path = str(found)
                else: 
                    logger.warning(f"⚠️ Email attachment not found: {file_path_raw}")
                    return f"Observation: Failed to send email. Attachment '{file_path_raw}' not found in workspace."

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
                    found = smart_file_finder(file_path_raw)
                    if found: 
                        attachment_abs_path = str(found)
                    else: 
                        logger.warning(f"⚠️ WhatsApp attachment not found: {file_path_raw}")
                        return f"Observation: Failed to send WhatsApp. Attachment '{file_path_raw}' not found."
                
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

        system_action = system_ctrl.get('system_action')
        if system_action:
            if system_action == 'screenshot':
                custom_filename = system_ctrl.get('screenshot_filename')
                from tools.workspace.workspace import workspace
                
                msg = SystemController.capture_screenshot(filename=custom_filename, save_dir=str(workspace.vault_dir))
                
                if "error" in msg.lower():
                    sys_observations.append(msg)
                else:
                    saved_name = custom_filename if custom_filename else msg.split("at: ")[1]
                    if saved_name and not saved_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        saved_name += ".png"
                    
                    try:
                        workspace.add_file_record(saved_name, "Vault", "Agent captured screenshot for screen analysis.")
                        workspace.sync_registry()
                    except Exception as reg_err:
                        logger.error(f"❌ Screenshot registry track failed: {reg_err}")
                        
                    sys_observations.append(f"Screenshot saved successfully as '{saved_name}' in Vault. To analyze what is on the screen, use 'workspace_action' with action='read' and file='{saved_name}' in your next step.")
            
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
                return f"Observation: Image successfully {action}d at {result_path}. It is now in the workspace."
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