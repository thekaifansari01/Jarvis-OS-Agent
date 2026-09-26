import os
import cv2
import time
import base64
import tempfile
import ctypes
import numpy as np
import pyautogui
from PIL import Image, ImageDraw, ImageFont
from core.logger.logger import logger

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

_gui_memory = {}

def _generate_som():
    logger.info("Capturing screen for GUI automation...")
    screenshot = pyautogui.screenshot()
    img_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 30, 150)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 4))
    dilated = cv2.dilate(edges, kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    overlay = screenshot.convert('RGBA')
    draw = ImageDraw.Draw(overlay)
    
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()

    ui_elements = {}
    element_id = 1
    
    box_color = (255, 0, 255, 180)
    tag_bg_color = (255, 0, 255, 230)
    tag_text_color = (255, 255, 255, 255)

    logger.debug("Scanning and tagging UI elements...")
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        
        if 10 < w < 1000 and 10 < h < 800:
            draw.rectangle([x, y, x + w, y + h], outline=box_color, width=2)
            
            tag = f"[{element_id}]"
            tag_width = len(tag) * 7 + 4
            
            draw.rectangle([x, max(0, y - 16), x + tag_width, y], fill=tag_bg_color)
            draw.text((x + 2, max(0, y - 15)), tag, fill=tag_text_color, font=font)
            
            center_x = x + (w // 2)
            center_y = y + (h // 2)
            ui_elements[element_id] = {'x': center_x, 'y': center_y}
            
            element_id += 1

    final_img = overlay.convert("RGB")
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, "jarvis_active_som.png")
    final_img.save(output_path)
    
    logger.info(f"Scan complete. Found {element_id - 1} UI zones.")
    return output_path, ui_elements


def handle_gui_controller(gui_cmd: dict):
    """
    NOTE: DO NOT wrap this function with @with_observation in executor.py.
    It returns a dictionary payload for images, which the decorator would break.
    """
    try:
        action = gui_cmd.get("action")
        
        if action == "observe":
            _gui_memory.clear()
            filepath, elements = _generate_som()
            _gui_memory.update(elements)
            
            with open(filepath, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            return {
                "type": "image_payload",
                "data": [{"mime_type": "image/png", "data": img_b64}],
                "observation": "Observation: Screen scanned and UI elements tagged with Magenta boxes. Look at the image and provide the exact 'element_id' to interact."
            }

        elif action in ["click", "type"]:
            raw_id = gui_cmd.get("element_id")
            
            if raw_id is None:
                return "Observation: Error -> Missing 'element_id'."
                
            # Safely cast AI output to integer
            try:
                elem_id = int(raw_id)
            except ValueError:
                return f"Observation: Error -> 'element_id' must be a valid number, got '{raw_id}'."
                
            if elem_id not in _gui_memory:
                return f"Observation: Error -> Element ID [{elem_id}] not found on current screen. Call 'observe' again to refresh."
                
            coords = _gui_memory[elem_id]
            x, y = coords["x"], coords["y"]
            
            if action == "click":
                logger.info(f"Executing click at ({x}, {y}) for element [{elem_id}]")
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.click()
                return f"Observation: Successfully clicked element [{elem_id}]."
                
            elif action == "type":
                text_to_type = gui_cmd.get("text", "")
                logger.info(f"Typing text into element [{elem_id}]")
                pyautogui.moveTo(x, y, duration=0.2)
                pyautogui.click()
                time.sleep(0.1) # UI ko active hone ka time dena chahiye
                pyautogui.write(text_to_type, interval=0.01)
                return f"Observation: Typed text into element [{elem_id}]."

        elif action == "press_key":
            key = gui_cmd.get("key")
            logger.info(f"Pressing key: {key}")
            pyautogui.press(key)
            return f"Observation: Pressed key '{key}'."

        elif action in ["scroll_down", "scroll_up"]:
            amount = -500 if action == "scroll_down" else 500
            logger.info(f"Scrolling screen: {action}")
            pyautogui.scroll(amount)
            return "Observation: Scrolled screen. UI layout changed. You MUST call 'observe' again before clicking anything."

        return "Observation: Unknown GUI action requested."
        
    except pyautogui.FailSafeException:
        logger.warning("PyAutoGUI FailSafe Triggered (Mouse pushed to corner).")
        return "Observation: Error -> Action aborted. The mouse was forcefully moved to the corner of the screen triggering the FailSafe."
    except Exception as e:
        logger.error(f"Failed to process GUI action: {e}")
        return f"Observation: Error executing GUI action -> {e}"