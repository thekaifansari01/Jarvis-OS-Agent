import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSION_DIR = os.path.join(BASE_DIR, "Data", "SessionCookies")
os.makedirs(SESSION_DIR, exist_ok=True)
SESSION_FILE = os.path.join(SESSION_DIR, "jarvis_telegram_session")


def _check_telegram_ready():
    if not API_ID or not API_HASH:
        return "Observation: Error -> TELEGRAM_API_ID or TELEGRAM_API_HASH missing in .env. ACTION_REQUIRED: Get credentials from https://my.telegram.org and add them to .env file, then restart Jarvis. Do NOT retry this tool."
    if not os.path.exists(f"{SESSION_FILE}.session"):
        return "Observation: Error -> Telegram not connected. ACTION_REQUIRED: User must run 'jarvis login --telegram' in a new terminal after closing Jarvis, then restart Jarvis. Do NOT retry this tool."
    return None


async def _send_msg(to_target, message, attachment_paths):
    ready_err = _check_telegram_ready()
    if ready_err:
        return ready_err

    if not to_target:
        return "Observation: Error -> Target recipient (username or phone number) is required."

    if not message and not attachment_paths:
        return "Observation: Error -> Both message and attachments cannot be empty."

    valid_attachments = [p for p in (attachment_paths or []) if os.path.exists(p)]
    missing_attachments = [p for p in (attachment_paths or []) if p and not os.path.exists(p)]
    if missing_attachments:
        return f"Observation: Error -> Attachment file(s) not found: {', '.join(missing_attachments)}. Provide valid absolute paths."

    try:
        async with TelegramClient(SESSION_FILE, API_ID, API_HASH) as client:
            if valid_attachments:
                await client.send_file(to_target, valid_attachments, caption=message)
                return f"Observation: Success -> Message with {len(valid_attachments)} attachment(s) sent to {to_target}."
            else:
                await client.send_message(to_target, message)
                return f"Observation: Success -> Message sent to {to_target}."
    except Exception as e:
        return f"Observation: Error -> Telegram send failed: {str(e)}. Verify the recipient username/number."


async def _fetch_chats(to_target, start_date, end_date):
    ready_err = _check_telegram_ready()
    if ready_err:
        return ready_err

    if not to_target or not start_date or not end_date:
        return "Observation: Error -> Target, start_date, and end_date are all required."

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError:
        return "Observation: Error -> Invalid date format. Use YYYY-MM-DD."

    try:
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
                return f"Observation: Info -> No conversation history found with {to_target} between {start_date} and {end_date}."

            header = chat_lines[0]
            body = chat_lines[1:][::-1]
            return "\n".join([header] + body)
    except Exception as e:
        return f"Observation: Error -> Telegram fetch failed: {str(e)}."


def send_telegram_message(to_target: str, message: str = "", attachment_paths: list = None) -> str:
    return asyncio.run(_send_msg(to_target, message, attachment_paths))


def fetch_telegram_chats(to_target: str, start_date: str, end_date: str) -> str:
    return asyncio.run(_fetch_chats(to_target, start_date, end_date))