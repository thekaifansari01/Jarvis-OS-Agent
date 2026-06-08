import os
from PIL import ImageGrab
from core.logger.logger import logger
from tools.workspace.workspace import workspace

def capture_screen(filename="screen.png"):
    """
    Captures the current screen and saves it to the Workspace Temp directory.
    Returns the absolute path of the saved image.
    """
    try:
        temp_dir = workspace.temp_dir
        file_path = temp_dir / filename

        logger.info("📸 Vision Tool: Capturing screen...")
        
        screenshot = ImageGrab.grab(all_screens=True) 
        
        screenshot.save(file_path)
        
        logger.info(f"✅ Screen captured successfully at: {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"❌ Screen capture failed: {e}")
        return None