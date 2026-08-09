import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSION_DIR = os.path.join(BASE_DIR, "Data", "SessionCookies")
os.makedirs(SESSION_DIR, exist_ok=True)
SESSION_FILE = os.path.join(SESSION_DIR, "jarvis_telegram_session")

async def _send_msg(to_target, message, attachment_paths):
    if not to_target:
        return "Error: Target is required."
    if not message and not attachment_paths:
        return "Error: Both message and attachments cannot be empty."

    valid_attachments = [p for p in (attachment_paths or []) if os.path.exists(p)]

    async with TelegramClient(SESSION_FILE, API_ID, API_HASH) as client:
        if valid_attachments:
            await client.send_file(to_target, valid_attachments, caption=message)
            return f"✅ Message with {len(valid_attachments)} attachment(s) sent to {to_target}."
        else:
            await client.send_message(to_target, message)
            return f"✅ Message successfully sent to {to_target}."

async def _fetch_chats(to_target, start_date, end_date):
    if not to_target or not start_date or not end_date:
        return "Error: Target, start_date, and end_date are required."

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError:
        return "Error: Invalid date format. Use YYYY-MM-DD."

    async with TelegramClient(SESSION_FILE, API_ID, API_HASH) as client:
        chat_lines = [f"[TELEGRAM CHAT HISTORY WITH {to_target.upper()} | {start_date} to {end_date}]"]
        count = 0
        async for msg in client.iter_messages(to_target, offset_date=end_dt):
            if msg.date < start_dt:
                break
            sender = "Me (Jarvis)" if msg.out else to_target.capitalize()
            msg_time = msg.date.strftime("%d %b, %H:%M")
            text = msg.text or ""
            if msg.media:
                text += " [Media Attachment]"
            chat_lines.append(f"[{msg_time}] {sender}: {text.strip()}")
            count += 1

        if count == 0:
            return f"No conversation history found with {to_target} between {start_date} and {end_date}."

        header = chat_lines[0]
        body = chat_lines[1:][::-1]
        return "\n".join([header] + body)

def send_telegram_message(to_target: str, message: str = "", attachment_paths: list = None) -> str:
    return asyncio.run(_send_msg(to_target, message, attachment_paths))

def fetch_telegram_chats(to_target: str, start_date: str, end_date: str) -> str:
    return asyncio.run(_fetch_chats(to_target, start_date, end_date))