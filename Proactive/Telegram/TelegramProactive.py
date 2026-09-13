import os
import asyncio
import threading
from collections import deque
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient

from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
JARVIS_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@").lower()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSION_DIR = os.path.join(BASE_DIR, "Data", "SessionCookies")
SESSION_FILE = os.path.join(SESSION_DIR, "jarvis_telegram_session")

MEDIA_VAULT_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'Jarvis', 'MediaVault', 'Telegram_Media')
os.makedirs(MEDIA_VAULT_DIR, exist_ok=True)

_stop_event = threading.Event()
_processed_msg_ids = deque(maxlen=5000)
_processed_msg_id_set = set()


def stop_telegram_listener():
    _stop_event.set()


def _already_processed(msg_id: int) -> bool:
    return msg_id in _processed_msg_id_set


def _mark_processed(msg_id: int):
    if msg_id in _processed_msg_id_set:
        return
    if len(_processed_msg_ids) == _processed_msg_ids.maxlen:
        old_id = _processed_msg_ids[0]
        _processed_msg_id_set.discard(old_id)
    _processed_msg_ids.append(msg_id)
    _processed_msg_id_set.add(msg_id)


def _is_jarvis_bot(entity) -> bool:
    if not JARVIS_BOT_USERNAME:
        return False
    username = (getattr(entity, 'username', '') or '').lstrip('@').lower()
    return username == JARVIS_BOT_USERNAME


async def telegram_listener_task():
    try:
        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start()

        logger.info("Jarvis Universal Telegram Listener connected to Proactive Queue...")

        while not _stop_event.is_set():
            loop_start = datetime.now(timezone.utc)

            try:
                async for dialog in client.iter_dialogs():
                    if not (dialog.is_user or dialog.is_group):
                        continue

                    entity = dialog.entity

                    if dialog.is_user and _is_jarvis_bot(entity):
                        continue

                    async for msg in client.iter_messages(entity, limit=10):
                        if msg.date < loop_start:
                            continue

                        if msg.out:
                            continue

                        if _already_processed(msg.id):
                            continue

                        _mark_processed(msg.id)

                        sender = getattr(entity, 'first_name', getattr(entity, 'title', 'Unknown'))
                        text = msg.text or ""
                        media_tag = ""

                        if msg.media:
                            try:
                                file_path = await client.download_media(message=msg, file=MEDIA_VAULT_DIR)
                                if file_path:
                                    abs_path = os.path.abspath(file_path).replace("\\", "/")
                                    media_tag = f"\n[Media Attachment Saved]: {abs_path}"
                                    logger.info(f"[TG MEDIA SAVED]: {abs_path}")
                            except Exception as dl_err:
                                logger.warning(f"Failed to download Telegram media: {dl_err}")

                        if not text and not media_tag:
                            continue

                        event_data = f"Sender: {sender}\nMessage: {text}{media_tag}"
                        push_proactive_event("Telegram", event_data, priority="high")
                        logger.info(f"New Telegram Alert from {sender}")

            except Exception as inner_err:
                logger.error(f"Telegram dialog iteration error: {inner_err}")

            await asyncio.sleep(3)

    except Exception as e:
        logger.error(f"Error in Telegram Proactive Listener: {e}")


def listen_for_telegram():
    if not API_ID or not API_HASH:
        logger.warning("Telegram API ID or Hash missing. Proactive listener disabled.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(telegram_listener_task())
    except Exception as e:
        logger.error(f"Telegram Listener Loop Crashed: {e}")
    finally:
        loop.close()