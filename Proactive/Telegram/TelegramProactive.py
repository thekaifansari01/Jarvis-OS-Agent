import os
import asyncio
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient

from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSION_DIR = os.path.join(BASE_DIR, "Data", "SessionCookies")
SESSION_FILE = os.path.join(SESSION_DIR, "jarvis_telegram_session")

MEDIA_VAULT_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'Jarvis', 'MediaVault', 'Telegram_Media')
os.makedirs(MEDIA_VAULT_DIR, exist_ok=True)

_stop_event = threading.Event()

def stop_telegram_listener():
    _stop_event.set()

async def telegram_listener_task():
    try:
        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start()
        
        start_time = datetime.now(timezone.utc)
        logger.info("Jarvis Universal Telegram Listener connected to Proactive Queue...")

        while not _stop_event.is_set():
            async for dialog in client.iter_dialogs():
                if dialog.is_user or dialog.is_group:
                    entity = dialog.entity
                    async for msg in client.iter_messages(entity, limit=5):
                        if msg.date < start_time or msg.out:
                            continue
                            
                        sender = getattr(entity, 'first_name', getattr(entity, 'title', 'Unknown'))
                        text = msg.text or ""
                        media_tag = ""

                        if msg.media:
                            try:
                                file_path = await client.download_media(message=msg, file=MEDIA_VAULT_DIR)
                                if file_path:
                                    abs_path = os.path.abspath(file_path).replace("\\", "/")
                                    media_tag = f"\n[Media Attachment Saved]: {abs_path}"
                                    logger.info(f"📎 [TG MEDIA SAVED]: {abs_path}")
                            except Exception as dl_err:
                                logger.warning(f"Failed to download Telegram media: {dl_err}")

                        event_data = f"Sender: {sender}\nMessage: {text}{media_tag}"
                        push_proactive_event("Telegram", event_data, priority="high")
                        logger.info(f"New Telegram Alert from {sender}")
            
            start_time = datetime.now(timezone.utc)
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