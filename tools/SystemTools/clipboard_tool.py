import pyperclip
from core.logger.logger import logger

def read_clipboard():
    """Reads text from the system clipboard."""
    try:
        content = pyperclip.paste()
        if content:
            logger.info("📋 Clipboard Tool: Read successful.")
            return content
        else:
            logger.info("📋 Clipboard Tool: Clipboard is empty.")
            return ""
    except Exception as e:
        logger.error(f"❌ Clipboard read failed: {e}")
        return None

def write_clipboard(text):
    """Writes text to the system clipboard."""
    try:
        pyperclip.copy(text)
        logger.info("📋 Clipboard Tool: Write successful.")
        return True
    except Exception as e:
        logger.error(f"❌ Clipboard write failed: {e}")
        return False