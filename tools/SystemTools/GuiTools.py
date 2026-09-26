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
            
            ui_elements[element_id] = {
                'cx': x + (w // 2), 
                'cy': y + (h // 2),
                'x': x,
                'y': y,
                'w': w,
                'h': h
            }
            
            element_id += 1

    final_img = overlay.convert("RGB")
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, "jarvis_active_som.png")
    final_img.save(output_path)
    
    logger.info(f"Scan complete. Found {element_id - 1} UI zones.")
    return output_path, ui_elements

def _get_target_coords(elem_id, position="center"):
    coords = _gui_memory[elem_id]
    if position == "top_left":
        return coords['x'] + 5, coords['y'] + 5
    elif position == "top_right":
        return coords['x'] + coords['w'] - 5, coords['y'] + 5
    elif position == "bottom_left":
        return coords['x'] + 5, coords['y'] + coords['h'] - 5
    elif position == "bottom_right":
        return coords['x'] + coords['w'] - 5, coords['y'] + coords['h'] - 5
    return coords['cx'], coords['cy']

def handle_gui_controller(gui_cmd: dict):
    try:
        action = gui_cmd.get("action")
        wait_time = float(gui_cmd.get("wait_after_action", 0.0))
        
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

        if action in ["click", "left_click", "right_click", "double_click", "hover", "type"]:
            raw_id = gui_cmd.get("element_id")
            position = gui_cmd.get("click_position", "center")
            
            if raw_id is None:
                return "Observation: Error -> Missing 'element_id'."
                
            try:
                elem_id = int(raw_id)
            except ValueError:
                return f"Observation: Error -> 'element_id' must be a valid number, got '{raw_id}'."
                
            if elem_id not in _gui_memory:
                return f"Observation: Error -> Element ID [{elem_id}] not found on current screen. Call 'observe' again to refresh."
                
            tx, ty = _get_target_coords(elem_id, position)
            logger.info(f"Executing {action} at ({tx}, {ty}) for element [{elem_id}]")
            
            pyautogui.moveTo(tx, ty, duration=0.2)
            
            if action in ["click", "left_click"]:
                pyautogui.click()
            elif action == "right_click":
                pyautogui.rightClick()
            elif action == "double_click":
                pyautogui.doubleClick()
            elif action == "type":
                pyautogui.click()
                time.sleep(0.1)
                pyautogui.write(gui_cmd.get("text", ""), interval=0.01)
                
            if wait_time > 0:
                time.sleep(wait_time)
                
            return f"Observation: Successfully performed {action} on element [{elem_id}] at position '{position}'."

        elif action == "drag_and_drop":
            start_id = gui_cmd.get("start_element_id")
            end_id = gui_cmd.get("end_element_id")
            
            if start_id is None or end_id is None:
                return "Observation: Error -> drag_and_drop requires 'start_element_id' and 'end_element_id'."
            
            try:
                start_id, end_id = int(start_id), int(end_id)
            except ValueError:
                return "Observation: Error -> IDs must be valid numbers."
                
            if start_id not in _gui_memory or end_id not in _gui_memory:
                return "Observation: Error -> One or both element IDs not found."
                
            sx, sy = _get_target_coords(start_id)
            ex, ey = _get_target_coords(end_id)
            
            logger.info(f"Dragging from [{start_id}] to [{end_id}]")
            pyautogui.moveTo(sx, sy, duration=0.2)
            pyautogui.dragTo(ex, ey, duration=0.5, button='left')
            
            if wait_time > 0:
                time.sleep(wait_time)
                
            return f"Observation: Successfully dragged from [{start_id}] to [{end_id}]."

        elif action == "press_key":
            key = gui_cmd.get("key")
            logger.info(f"Pressing key: {key}")
            pyautogui.press(key)
            if wait_time > 0: time.sleep(wait_time)
            return f"Observation: Pressed key '{key}'."
            
        elif action == "hotkey":
            keys = gui_cmd.get("keys", [])
            if not isinstance(keys, list) or not keys:
                return "Observation: Error -> 'keys' array is missing or empty."
            logger.info(f"Pressing hotkey: {keys}")
            pyautogui.hotkey(*keys)
            if wait_time > 0: time.sleep(wait_time)
            return f"Observation: Pressed hotkey combo {keys}."

        elif action in ["scroll_down", "scroll_up"]:
            amount = -500 if action == "scroll_down" else 500
            logger.info(f"Scrolling screen: {action}")
            pyautogui.scroll(amount)
            if wait_time > 0: time.sleep(wait_time)
            return "Observation: Scrolled screen. UI layout changed. You MUST call 'observe' again before clicking anything."

        return "Observation: Unknown GUI action requested."
        
    except pyautogui.FailSafeException:
        logger.warning("PyAutoGUI FailSafe Triggered.")
        return "Observation: Error -> Action aborted. The mouse was forcefully moved to the corner of the screen triggering the FailSafe."
    except Exception as e:
        logger.error(f"Failed to process GUI action: {e}")
        return f"Observation: Error executing GUI action -> {e}"