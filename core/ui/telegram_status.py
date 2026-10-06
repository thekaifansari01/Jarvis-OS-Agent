import re

ACTIVE_TELEGRAM_CHAT_ID = None
TELEGRAM_SENDER = None

def set_telegram_context(chat_id, sender_func):
    global ACTIVE_TELEGRAM_CHAT_ID, TELEGRAM_SENDER
    ACTIVE_TELEGRAM_CHAT_ID = chat_id
    TELEGRAM_SENDER = sender_func

def clear_telegram_context():
    global ACTIVE_TELEGRAM_CHAT_ID, TELEGRAM_SENDER
    ACTIVE_TELEGRAM_CHAT_ID = None
    TELEGRAM_SENDER = None

def escape_markdown(text):
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))

def send_telegram_update(step=None, thought=None, action=None, observation=None, final_response=None):
    if not ACTIVE_TELEGRAM_CHAT_ID or not TELEGRAM_SENDER:
        return

    if final_response:
        msg = f"🎯 *Task Complete*\n\n{escape_markdown(final_response)}"
        TELEGRAM_SENDER(ACTIVE_TELEGRAM_CHAT_ID, msg)
        return

    msg_parts = []
    if step is not None:
        msg_parts.append(f"🔄 *Step:* {escape_markdown(step)}")
    if thought:
        msg_parts.append(f"🧠 *Thought:* {escape_markdown(thought)}")
    if action:
        msg_parts.append(f"🛠 *Action:* {escape_markdown(action)}")
    if observation:
        obs_trunc = str(observation)[:500] + ("..." if len(str(observation)) > 500 else "")
        msg_parts.append(f"👁 *Observation:* {escape_markdown(obs_trunc)}")

    if msg_parts:
        TELEGRAM_SENDER(ACTIVE_TELEGRAM_CHAT_ID, "\n\n".join(msg_parts))