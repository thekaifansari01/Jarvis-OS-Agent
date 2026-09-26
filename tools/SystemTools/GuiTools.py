import os
import time
import base64
import tempfile
import ctypes
import pyautogui
from PIL import Image, ImageDraw, ImageFont
from core.logger.logger import logger

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def _draw_rulers(img):
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grid_color = (0, 255, 255, 40)
    grid_mid = (255, 255, 0, 30)

    for x in range(100, w, 100):
        od.line([(x, 0), (x, h)], fill=grid_color, width=1)
    for x in range(50, w, 100):
        od.line([(x, 0), (x, h)], fill=grid_mid, width=1)
    for y in range(100, h, 100):
        od.line([(0, y), (w, y)], fill=grid_color, width=1)
    for y in range(50, h, 100):
        od.line([(0, y), (w, y)], fill=grid_mid, width=1)

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_major = None
    font_minor = None
    for fname in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf",
                  "DejaVuSans.ttf", "LiberationSans-Bold.ttf"):
        try:
            font_major = ImageFont.truetype(fname, 14)
            font_minor = ImageFont.truetype(fname, 11)
            break
        except Exception:
            continue
    if font_major is None:
        font_major = ImageFont.load_default()
        font_minor = font_major

    RULER = 30
    BG = (10, 10, 10, 255)
    MAJOR = (0, 255, 255, 255)
    MEDIUM = (255, 220, 0, 255)
    MINOR = (170, 170, 170, 255)
    TEXT = (255, 255, 255, 255)
    ACCENT_BG = (40, 40, 40, 255)

    draw.rectangle([0, 0, w, RULER], fill=BG)
    draw.rectangle([0, 0, RULER, h], fill=BG)
    draw.rectangle([0, 0, RULER, RULER], fill=ACCENT_BG)

    for x in range(0, w, 10):
        if x % 100 == 0:
            draw.line([(x, 0), (x, RULER)], fill=MAJOR, width=2)
            draw.text((x + 3, 4), str(x), fill=TEXT, font=font_major)
        elif x % 50 == 0:
            draw.line([(x, RULER - 12), (x, RULER)], fill=MEDIUM, width=2)
            draw.text((x + 2, RULER - 16), str(x), fill=MEDIUM, font=font_minor)
        else:
            draw.line([(x, RULER - 5), (x, RULER)], fill=MINOR, width=1)

    for y in range(0, h, 10):
        if y % 100 == 0:
            draw.line([(0, y), (RULER, y)], fill=MAJOR, width=2)
            draw.text((3, y + 3), str(y), fill=TEXT, font=font_major)
        elif y % 50 == 0:
            draw.line([(RULER - 12, y), (RULER, y)], fill=MEDIUM, width=2)
            draw.text((RULER - 22, y + 2), str(y), fill=MEDIUM, font=font_minor)
        else:
            draw.line([(RULER - 5, y), (RULER, y)], fill=MINOR, width=1)

    draw.text((4, 8), "0,0", fill=MAJOR, font=font_minor)
    draw.text((w - 60, 6), "X ->", fill=MAJOR, font=font_major)
    draw.text((4, h - 22), "Y v", fill=MAJOR, font=font_major)

    draw.line([(0, RULER), (w, RULER)], fill=MAJOR, width=1)
    draw.line([(RULER, 0), (RULER, h)], fill=MAJOR, width=1)

    return img


def _capture_ruler_screen():
    logger.info("Capturing screen and drawing axis rulers...")
    screenshot = pyautogui.screenshot()
    w, h = screenshot.size
    annotated_img = _draw_rulers(screenshot)
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, "jarvis_ruler_screen.png")
    annotated_img.save(output_path)
    return output_path, w, h


def handle_gui_controller(gui_cmd: dict):
    try:
        action = gui_cmd.get("action")
        wait_time = float(gui_cmd.get("wait_after_action", 0.0))

        if action == "observe":
            filepath, width, height = _capture_ruler_screen()

            with open(filepath, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            return {
                "type": "image_payload",
                "data": [{"mime_type": "image/png", "data": img_b64}],
                "observation": (
                    f"Observation: Screen captured. Resolution: {width}x{height}. "
                    "Top ruler = X axis (cyan ticks every 100px, yellow every 50px). "
                    "Left ruler = Y axis (cyan ticks every 100px, yellow every 50px). "
                    "Faint cyan/yellow grid lines also cross the screen at those intervals. "
                    "Use these rulers + grid intersections to compute EXACT (X, Y) coordinates "
                    "for any UI element before clicking."
                )
            }

        if action in ["click", "left_click", "right_click", "double_click", "hover", "type"]:
            x = gui_cmd.get("x")
            y = gui_cmd.get("y")

            if x is None or y is None:
                return "Observation: Error -> Missing 'x' or 'y' coordinates."

            try:
                x, y = int(x), int(y)
            except ValueError:
                return "Observation: Error -> 'x' and 'y' must be valid integers."

            logger.info(f"Executing {action} at ({x}, {y})")
            pyautogui.moveTo(x, y, duration=0.2)

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

            return f"Observation: Successfully performed {action} at ({x}, {y})."

        elif action == "drag_and_drop":
            sx = gui_cmd.get("start_x")
            sy = gui_cmd.get("start_y")
            ex = gui_cmd.get("end_x")
            ey = gui_cmd.get("end_y")

            if None in [sx, sy, ex, ey]:
                return "Observation: Error -> drag_and_drop requires start_x, start_y, end_x, end_y."

            try:
                sx, sy, ex, ey = int(sx), int(sy), int(ex), int(ey)
            except ValueError:
                return "Observation: Error -> Coordinates must be valid integers."

            logger.info(f"Dragging from ({sx}, {sy}) to ({ex}, {ey})")
            pyautogui.moveTo(sx, sy, duration=0.2)
            pyautogui.dragTo(ex, ey, duration=0.5, button='left')

            if wait_time > 0:
                time.sleep(wait_time)

            return f"Observation: Successfully dragged from ({sx}, {sy}) to ({ex}, {ey})."

        elif action == "press_key":
            key = gui_cmd.get("key")
            logger.info(f"Pressing key: {key}")
            pyautogui.press(key)
            if wait_time > 0:
                time.sleep(wait_time)
            return f"Observation: Pressed key '{key}'."

        elif action == "hotkey":
            keys = gui_cmd.get("keys", [])
            if not isinstance(keys, list) or not keys:
                return "Observation: Error -> 'keys' array is missing or empty."
            logger.info(f"Pressing hotkey: {keys}")
            pyautogui.hotkey(*keys)
            if wait_time > 0:
                time.sleep(wait_time)
            return f"Observation: Pressed hotkey combo {keys}."

        elif action in ["scroll_down", "scroll_up"]:
            amount = -500 if action == "scroll_down" else 500
            logger.info(f"Scrolling screen: {action}")
            pyautogui.scroll(amount)
            if wait_time > 0:
                time.sleep(wait_time)
            return "Observation: Scrolled screen. You MUST call 'observe' again to see updated UI."

        return "Observation: Unknown GUI action requested."

    except pyautogui.FailSafeException:
        logger.warning("PyAutoGUI FailSafe Triggered.")
        return "Observation: Error -> Action aborted. Mouse pushed to corner triggering FailSafe."
    except Exception as e:
        logger.error(f"Failed to process GUI action: {e}")
        return f"Observation: Error executing GUI action -> {e}"