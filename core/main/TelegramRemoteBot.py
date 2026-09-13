import os
import time
import threading
import re
from concurrent.futures import ThreadPoolExecutor
import telebot
from core.security import load_decrypted_token
from core.main.CommandHandler import main_command_processor, is_jarvis_busy
from core.ui.telegram_status import set_telegram_context, clear_telegram_context

_bot_instance = None
_bot_thread = None
_is_polling = False
_global_executor = None
_global_memory = None

def get_token_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "Data", "SessionCookies", "telegram_bot_token.enc")

def set_telegram_remote_context(executor: ThreadPoolExecutor, memory):
    global _global_executor, _global_memory
    _global_executor = executor
    _global_memory = memory

def _telegram_sender_callback(chat_id, message_text):
    if _bot_instance:
        try:
            _bot_instance.send_message(chat_id, message_text, parse_mode="MarkdownV2")
        except Exception:
            try:
                _bot_instance.send_message(chat_id, message_text)
            except Exception:
                pass

def start_telegram_remote_listener():
    global _bot_instance, _bot_thread, _is_polling

    token_path = get_token_path()
    if not os.path.exists(token_path):
        return False

    try:
        data = load_decrypted_token(token_path)
        if not data:
            return False

        token = data.get("token")
        allowed_chat_id = data.get("allowed_chat_id")

        if not token:
            return False

        if _is_polling and _bot_instance:
            return True

        _bot_instance = telebot.TeleBot(token)
        _is_polling = True

        @_bot_instance.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            msg = "🤖 *Jarvis Remote Controller Bot Active!*\n\nSend any text command to execute on your PC."
            _bot_instance.reply_to(message, msg, parse_mode="Markdown")

        @_bot_instance.message_handler(func=lambda message: True)
        def handle_remote_command(message):
            if allowed_chat_id and str(message.chat.id) != str(allowed_chat_id):
                return

            cmd_text = message.text.strip() if message.text else ""
            if not cmd_text:
                return

            is_silent = False
            if cmd_text.lower().startswith('/silent'):
                is_silent = True
                cmd_text = re.sub(r'(?i)^/silent\s*', '', cmd_text).strip()
                if not cmd_text:
                    return

            if is_jarvis_busy():
                if _global_memory and hasattr(_global_memory, 'add_live_feedback'):
                    _global_memory.add_live_feedback(cmd_text)
            else:
                if _global_memory:
                    if not hasattr(_global_memory, "ephemeral"):
                        _global_memory.ephemeral = {}
                    _global_memory.ephemeral["force_silent_agentic"] = is_silent
                    
                set_telegram_context(message.chat.id, _telegram_sender_callback)
                
                if _global_executor and _global_memory:
                    _global_executor.submit(main_command_processor, cmd_text, _global_executor, _global_memory, "telegram_bot")

        def _poll_worker():
            global _is_polling
            retries = 0
            while _is_polling:
                try:
                    _bot_instance.infinity_polling(timeout=20, long_polling_timeout=10)
                    break
                except Exception as e:
                    error_msg = str(e).lower()
                    if "polling exited" in error_msg or "break infinity polling" in error_msg:
                        break
                    retries += 1
                    if retries >= 5:
                        _is_polling = False
                        break
                    time.sleep(5)
            _is_polling = False

        _bot_thread = threading.Thread(target=_poll_worker, daemon=True)
        _bot_thread.start()
        return True

    except Exception:
        _is_polling = False
        return False

def stop_telegram_remote_listener():
    global _bot_instance, _is_polling
    if _bot_instance and _is_polling:
        try:
            _bot_instance.stop_bot()
            _bot_instance.stop_polling()
        except Exception:
            pass
        finally:
            _is_polling = False
            _bot_instance = None
            clear_telegram_context()

def is_telegram_remote_running() -> bool:
    global _is_polling
    return _is_polling