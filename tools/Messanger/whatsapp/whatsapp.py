import os
import json
import logging
import requests
from datetime import datetime

CONTACTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
    "Data", 
    "contacts.json"
)

def load_contacts():
    if not os.path.exists(CONTACTS_FILE):
        logging.warning(f"⚠️ contacts.json file not found at path: {CONTACTS_FILE}")
        return {}
    
    try:
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"❌ [CRITICAL] contacts.json is corrupted or has an invalid format: {e}")
        return {}
    except Exception as e:
        logging.error(f"❌ [ERROR] Failed to load contacts: {e}")
        return {}

def send_whatsapp_message(to_target: str, message: str = "", attachment_path: str = None) -> str:
    if not to_target:
        return "❌ Error: Target (Name or Number) is required."

    if not message and not attachment_path:
        return "❌ Error: Both message text and attachment cannot be empty."

    clean_target = to_target.strip()
    target_number = None

    cleaned_num = clean_target.replace("+", "").replace(" ", "").replace("-", "")

    if cleaned_num.isdigit():
        if len(cleaned_num) == 10:
            target_number = "91" + cleaned_num
            logging.info(f"🔢 10-Digit number detected, added default country code '91': {target_number}")
        else:
            target_number = cleaned_num
            logging.info(f"🔢 Direct number detected: {target_number}")
    else:
        contacts = load_contacts()
        target_number = contacts.get(clean_target.lower())
        if not target_number:
            return f"❌ Number for '{clean_target}' not found in contacts.json, and it is not a valid direct number."
        logging.info(f"👤 Contact detected: {clean_target} -> {target_number}")

    if attachment_path:
        if not os.path.exists(attachment_path):
            error_msg = f"❌ Workspace file not found: {attachment_path}"
            logging.error(error_msg)
            return error_msg
        
        if not os.access(attachment_path, os.R_OK):
            error_msg = f"❌ Missing read permission for file: {attachment_path}"
            logging.error(error_msg)
            return error_msg

    local_baileys_url = "http://localhost:3000/send"
    
    payload = {
        "number": target_number,
        "message": message,
        "file_path": attachment_path  
    }

    try:
        logging.info(f"🚀 Sending command to local Baileys bridge for {clean_target}...")
        
        response = requests.post(local_baileys_url, json=payload, timeout=20)
        
        if response.status_code == 200:
            status_text = "✅ WhatsApp message (with attachment)" if attachment_path else "✅ WhatsApp message"
            success_text = f"{status_text} successfully sent to {clean_target} via Baileys."
            logging.info(success_text)
            return success_text
        else:
            error_text = f"❌ Baileys Server Error (Code {response.status_code}): {response.text}"
            logging.error(error_text)
            return error_text
            
    except requests.exceptions.ConnectionError:
        error_msg = "❌ Node.js server is offline! Please start 'node baileys_service.js' in the BaileysServer directory first."
        logging.error(error_msg)
        return error_msg
    except requests.exceptions.Timeout:
        error_msg = "❌ Timeout Error: Node.js server did not respond within 20 seconds. The engine might be hanging."
        logging.error(error_msg)
        return error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"❌ API Request failed: {e}"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Unexpected Python Error: {e}"
        logging.error(error_msg)
        return error_msg

def fetch_whatsapp_chats(to_target: str, start_date: str, end_date: str) -> str:
    if not to_target or not start_date or not end_date:
        return "❌ Error: Target, start_date, and end_date are all required."

    clean_target = to_target.strip()
    target_number = None

    cleaned_num = clean_target.replace("+", "").replace(" ", "").replace("-", "")

    if cleaned_num.isdigit():
        if len(cleaned_num) == 10:
            target_number = "91" + cleaned_num
        else:
            target_number = cleaned_num
    else:
        contacts = load_contacts()
        target_number = contacts.get(clean_target.lower())
        if not target_number:
            return f"❌ Number for '{clean_target}' not found in contacts.json, and it is not a valid direct number."

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        start_timestamp = int(start_dt.timestamp())
        
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
        end_timestamp = int(end_dt.timestamp())
    except ValueError:
        return "❌ Error: Invalid date format. Please use YYYY-MM-DD exactly."

    local_baileys_url = "http://localhost:3000/fetch-chats"
    
    payload = {
        "number": target_number,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp
    }

    try:
        logging.info(f"📥 Fetching chats for {clean_target} from Baileys bridge...")
        
        response = requests.post(local_baileys_url, json=payload, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            messages = data.get("messages", [])
            
            if not messages:
                return f"Observation: No conversation history found with {clean_target} between {start_date} and {end_date}."
            
            chat_lines = [f"📱 [CHAT HISTORY WITH {clean_target.upper()} | {start_date} to {end_date}]"]
            for msg in messages:
                sender = "Me (Jarvis)" if msg.get("fromMe") else clean_target.capitalize()
                msg_time = datetime.fromtimestamp(msg.get("timestamp")).strftime("%d %b, %H:%M")
                text = msg.get("text", "[Media/Unknown]")
                chat_lines.append(f"[{msg_time}] {sender}: {text}")
            
            success_text = "\n".join(chat_lines)
            logging.info(f"✅ Fetched {len(messages)} messages successfully.")
            return success_text
        else:
            error_text = f"❌ Baileys Server Error (Code {response.status_code}): {response.text}"
            logging.error(error_text)
            return error_text
            
    except requests.exceptions.ConnectionError:
        error_msg = "❌ Node.js server is offline! Please start 'node baileys_service.js' in the BaileysServer directory first."
        logging.error(error_msg)
        return error_msg
    except requests.exceptions.Timeout:
        error_msg = "❌ Timeout Error: Node.js server did not respond within 20 seconds."
        logging.error(error_msg)
        return error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"❌ API Request failed: {e}"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Unexpected Python Error: {e}"
        logging.error(error_msg)
        return error_msg