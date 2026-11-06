import pyperclip
from core.logger.logger import logger


def read_clipboard():
    try:
        content = pyperclip.paste()
        if content:
            logger.info("📋 Clipboard Tool: Read successful.")
            return f"Observation: Success -> Clipboard content: {content}"
        else:
            logger.info("📋 Clipboard Tool: Clipboard is empty.")
            return "Observation: Info -> Clipboard is empty."
    except Exception as e:
        logger.error(f"❌ Clipboard read failed: {e}")
        return f"Observation: Error -> Clipboard read failed: {str(e)}."


def write_clipboard(text):
    try:
        pyperclip.copy(text)
        logger.info("📋 Clipboard Tool: Write successful.")
        return f"Observation: Success -> Copied {len(text)} characters to clipboard."
    except Exception as e:
        logger.error(f"❌ Clipboard write failed: {e}")
        return f"Observation: Error -> Clipboard write failed: {str(e)}."