import os
import time
import base64
import tempfile
import ctypes
import hashlib
import threading
import difflib
import pyautogui
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from core.logger.logger import logger

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.04

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

_RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
_RESAMPLE_BILINEAR = getattr(Image, "Resampling", Image).BILINEAR

_ocr_engine = None
_ocr_lock = threading.Lock()
_LAST_ELEMENTS = []
_LAST_SCREEN_HASH = None
_CACHE_LOCK = threading.Lock()
_MAX_ELEMENTS = 200
_DEFAULT_POST_ACTION_WAIT = 0.5

_INTERACTIVE_UIA_ROLES = {
    "ButtonControl", "EditControl", "HyperlinkControl", "MenuItemControl",
    "ComboBoxControl", "CheckBoxControl", "RadioButtonControl", "ListItemControl",
    "TabItemControl", "TreeItemControl", "DataItemControl", "SpinnerControl",
    "SliderControl", "SplitButtonControl", "TextControl", "DocumentControl",
}

_CONTAINER_UIA_ROLES = {
    "WindowControl", "PaneControl", "GroupControl", "CustomControl",
    "ToolBarControl", "MenuBarControl", "StatusBarControl", "ScrollBarControl",
    "TitleBarControl", "HeaderControl",
}


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine

    with _ocr_lock:
        if _ocr_engine is not None:
            return _ocr_engine

        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
            logger.info("RapidOCR initialized.")
        except Exception as e:
            logger.warning(f"RapidOCR init failed: {e}")
            _ocr_engine = False

    return _ocr_engine


def warmup_gui_system():
    hr = None
    try:
        hr = ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass
    try:
        logger.info("Loading GUI Grounding System (RapidOCR + UIA)...")

        ocr = _get_ocr()
        if ocr:
            dummy = np.zeros((64, 64, 3), dtype=np.uint8)
            try:
                ocr(dummy)
                logger.info("RapidOCR warmup complete.")
            except Exception as e:
                logger.warning(f"OCR warmup inference failed: {e}")

        try:
            import uiautomation
            _ = uiautomation.GetForegroundControl()
            logger.info("UIA warmup complete.")
        except Exception as e:
            logger.warning(f"UIA warmup failed: {e}")

        logger.info("GUI Grounding System ready.")
    except Exception as e:
        logger.warning(f"GUI system warmup failed: {e}")
    finally:
        if hr in (0, 1):
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass


def _compute_screen_hash(img):
    small = img.resize((384, 216), _RESAMPLE_BILINEAR)
    quantized = small.point(lambda p: (p // 4) * 4)
    return hashlib.md5(quantized.tobytes()).hexdigest()


def _capture_rgb():
    try:
        return pyautogui.screenshot().convert("RGB")
    except Exception:
        return None


def _has_screen_changed(before_img, after_img, target_xy=None):
    if before_img is None or after_img is None:
        return True
    if _compute_screen_hash(before_img) != _compute_screen_hash(after_img):
        return True
    if target_xy is not None:
        tx, ty = target_xy
        w, h = before_img.size
        x1, y1 = max(0, tx - 160), max(0, ty - 100)
        x2, y2 = min(w, tx + 160), min(h, ty + 100)
        if x2 > x1 and y2 > y1:
            b_arr = np.asarray(before_img.crop((x1, y1, x2, y2)), dtype=np.float32)
            a_arr = np.asarray(after_img.crop((x1, y1, x2, y2)), dtype=np.float32)
            diff = np.abs(b_arr - a_arr)
            if diff.mean() > 0.9 or diff.max() > 24.0:
                return True
    return False


def _invalidate_cache():
    global _LAST_SCREEN_HASH
    with _CACHE_LOCK:
        _LAST_SCREEN_HASH = None


def _detect_text_elements(img):
    ocr = _get_ocr()
    if not ocr:
        return []

    orig_w, orig_h = img.size
    scale = 1.0
    work_img = img
    if orig_w > 1920:
        scale = 1920.0 / orig_w
        new_size = (int(orig_w * scale), int(orig_h * scale))
        work_img = img.resize(new_size, _RESAMPLE_LANCZOS)

    arr = np.array(work_img)
    elements = []

    try:
        result, _ = ocr(arr)
        if result:
            for item in result:
                try:
                    box, text, conf = item[0], item[1], float(item[2])
                    clean_text = str(text).strip()
                    if conf < 0.45 or not clean_text:
                        continue
                    xs = [p[0] / scale for p in box]
                    ys = [p[1] / scale for p in box]
                    x1 = max(0, min(orig_w, int(round(min(xs)))))
                    y1 = max(0, min(orig_h, int(round(min(ys)))))
                    x2 = max(0, min(orig_w, int(round(max(xs)))))
                    y2 = max(0, min(orig_h, int(round(max(ys)))))
                    if (x2 - x1) < 3 or (y2 - y1) < 3:
                        continue
                    elements.append({
                        "text": clean_text,
                        "bbox": (x1, y1, x2, y2),
                        "role": "text",
                        "source": "ocr",
                    })
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"RapidOCR inference failed: {e}")

    return elements


def _extract_uia_label(ctrl, role):
    try:
        name = (ctrl.Name or "").strip()
        if name:
            return name
    except Exception:
        pass

    try:
        val_pat = ctrl.GetValuePattern()
        if val_pat:
            val = (val_pat.Value or "").strip()
            if val:
                return val[:70]
    except Exception:
        pass

    try:
        legacy = ctrl.GetLegacyIAccessiblePattern()
        if legacy:
            leg_name = (legacy.Name or "").strip()
            if leg_name:
                return leg_name[:70]
    except Exception:
        pass

    try:
        help_text = (ctrl.HelpText or "").strip()
        if help_text:
            return help_text[:70]
    except Exception:
        pass

    try:
        auto_id = (ctrl.AutomationId or "").strip()
    except Exception:
        auto_id = ""

    if role in ("EditControl", "ComboBoxControl", "DocumentControl"):
        if auto_id and not auto_id.isdigit():
            return f"Input ({auto_id})"
        return "Input Field"

    if role in ("ButtonControl", "SplitButtonControl", "CheckBoxControl", "RadioButtonControl"):
        if auto_id and not auto_id.isdigit():
            return auto_id

    return ""


def _detect_uia_elements(screen_size):
    try:
        import uiautomation as auto
    except ImportError:
        return []

    hr = None
    try:
        hr = ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass

    screen_w, screen_h = screen_size
    screen_area = max(1, screen_w * screen_h)
    elements = []
    seen_keys = set()
    deadline = time.perf_counter() + 1.8

    def walk(ctrl, depth=0, max_depth=16):
        if depth > max_depth or len(elements) >= 240 or time.perf_counter() > deadline:
            return
        try:
            children = ctrl.GetChildren()
        except Exception:
            return

        for child in children:
            if time.perf_counter() > deadline or len(elements) >= 240:
                break
            try:
                try:
                    if child.IsOffscreen:
                        continue
                except Exception:
                    pass

                rect = child.BoundingRectangle
                if not rect:
                    continue

                x1 = max(0, int(rect.left))
                y1 = max(0, int(rect.top))
                x2 = min(screen_w, int(rect.right))
                y2 = min(screen_h, int(rect.bottom))
                w = x2 - x1
                h = y2 - y1

                if w < 5 or h < 5:
                    continue

                role = getattr(child, "ControlTypeName", "") or "Control"
                area = w * h

                if role in _CONTAINER_UIA_ROLES and area > 0.12 * screen_area:
                    walk(child, depth + 1, max_depth)
                    continue

                if role == "DocumentControl" and area > 0.20 * screen_area:
                    walk(child, depth + 1, max_depth)
                    continue

                if role in _INTERACTIVE_UIA_ROLES or area <= 0.08 * screen_area:
                    label = _extract_uia_label(child, role)
                    if label:
                        clean_role = role.replace("Control", "").lower() or "control"
                        dedup_key = (x1 // 4, y1 // 4, x2 // 4, y2 // 4, label.lower())
                        if dedup_key not in seen_keys:
                            seen_keys.add(dedup_key)
                            elements.append({
                                "text": label,
                                "bbox": (x1, y1, x2, y2),
                                "role": clean_role,
                                "source": "uia",
                            })
            except Exception:
                pass

            walk(child, depth + 1, max_depth)

    try:
        fg = auto.GetForegroundControl()
        if fg:
            walk(fg, depth=0, max_depth=16)

        if time.perf_counter() <= deadline:
            root = auto.GetRootControl()
            if root:
                for win in root.GetChildren():
                    if time.perf_counter() > deadline:
                        break
                    try:
                        cls_name = (win.ClassName or "").strip()
                        if cls_name in ("Shell_TrayWnd", "NotifyIconOverflowWindow", "#32768"):
                            walk(win, depth=0, max_depth=6)
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"UIA detection failed: {e}")
    finally:
        if hr in (0, 1):
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    return elements


def _merge_elements(text_els, uia_els):
    merged = []
    for u in uia_els:
        ux1, uy1, ux2, uy2 = u["bbox"]
        u_area = max(1, (ux2 - ux1) * (uy2 - uy1))
        u_text = u["text"].strip().lower()
        duplicate_uia = False
        for existing in merged:
            ex1, ey1, ex2, ey2 = existing["bbox"]
            e_area = max(1, (ex2 - ex1) * (ey2 - ey1))
            ix = max(0, min(ux2, ex2) - max(ux1, ex1))
            iy = max(0, min(uy2, ey2) - max(uy1, ey1))
            inter = ix * iy
            if inter > 0.75 * min(u_area, e_area) and u_text == existing["text"].strip().lower():
                duplicate_uia = True
                break
        if not duplicate_uia:
            merged.append(dict(u))

    for t in text_els:
        tx1, ty1, tx2, ty2 = t["bbox"]
        t_area = max(1, (tx2 - tx1) * (ty2 - ty1))
        tcx = (tx1 + tx2) * 0.5
        tcy = (ty1 + ty2) * 0.5
        dup = False

        for u in merged:
            ux1, uy1, ux2, uy2 = u["bbox"]
            u_area = max(1, (ux2 - ux1) * (uy2 - uy1))
            if u_area > 6 * t_area:
                continue

            ix = max(0, min(tx2, ux2) - max(tx1, ux1))
            iy = max(0, min(ty2, uy2) - max(ty1, uy1))
            inter = ix * iy
            center_inside = (ux1 <= tcx <= ux2) and (uy1 <= tcy <= uy2)

            if inter > 0.45 * min(t_area, u_area) or (center_inside and u_area <= 4.5 * t_area):
                if u["text"].startswith("Input") and t["text"] and t["text"].lower() not in u["text"].lower():
                    u["text"] = f"{u['text']}: {t['text']}"
                dup = True
                break

        if not dup:
            merged.append(dict(t))

    merged.sort(key=lambda e: (e["bbox"][1] // 18, e["bbox"][0]))
    return merged[:_MAX_ELEMENTS]


def _load_font(size):
    candidates = [
        "arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "tahomabd.ttf",
        "arial.ttf", "segoeui.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_marks(img, elements):
    marked = img.copy().convert("RGB")
    draw = ImageDraw.Draw(marked, "RGBA")
    font_small = _load_font(12)
    w, h = marked.size
    placed_badges = []
    centers = [_element_center(el) for el in elements]

    for i, el in enumerate(elements, start=1):
        x1, y1, x2, y2 = el["bbox"]
        pad = 1
        rx1, ry1 = max(0, x1 - pad), max(0, y1 - pad)
        rx2, ry2 = min(w - 1, x2 + pad), min(h - 1, y2 + pad)

        outline_color = (255, 0, 0, 235) if el.get("source") == "ocr" else (0, 170, 255, 235)
        draw.rectangle([rx1, ry1, rx2, ry2], outline=outline_color, width=2)

        badge = str(i)
        try:
            bbox = draw.textbbox((0, 0), badge, font=font_small)
            bw = bbox[2] - bbox[0]
            bh = bbox[3] - bbox[1]
        except Exception:
            bw, bh = 10, 12

        pad_w = bw + 8
        pad_h = bh + 6

        candidates = [
            (rx1, max(0, ry1 - pad_h - 1)),
            (max(0, rx1 - pad_w - 1), ry1),
            (rx1, min(h - pad_h, ry2 + 1)),
            (min(w - pad_w, rx2 - pad_w), max(0, ry1 - pad_h - 1)),
            (rx1 + 1, ry1 + 1),
        ]

        bx1, by1 = candidates[0]
        for cx, cy in candidates:
            cbx2 = min(w, cx + pad_w)
            cby2 = min(h, cy + pad_h)
            badge_overlap = any(
                not (cbx2 < px1 or cx > px2 or cby2 < py1 or cy > py2)
                for (px1, py1, px2, py2) in placed_badges
            )
            center_overlap = any(
                idx != (i - 1) and (cx <= ecx <= cbx2 and cy <= ecy <= cby2)
                for idx, (ecx, ecy) in enumerate(centers)
            )
            if not badge_overlap and not center_overlap:
                bx1, by1 = cx, cy
                break

        bx2 = min(w, bx1 + pad_w)
        by2 = min(h, by1 + pad_h)
        placed_badges.append((bx1, by1, bx2, by2))

        draw.rectangle([bx1, by1, bx2, by2], fill=(255, 220, 0, 245), outline=(0, 0, 0, 255), width=1)
        draw.text((bx1 + 4, by1 + 2), badge, fill=(0, 0, 0, 255), font=font_small)

    return marked


def _capture_grounded_screen():
    global _LAST_ELEMENTS, _LAST_SCREEN_HASH

    screenshot = pyautogui.screenshot().convert("RGB")
    curr_hash = _compute_screen_hash(screenshot)
    out_path = os.path.join(tempfile.gettempdir(), "jarvis_som_screen.png")

    with _CACHE_LOCK:
        if curr_hash == _LAST_SCREEN_HASH and _LAST_ELEMENTS:
            logger.info(f"Screen unchanged - reusing {len(_LAST_ELEMENTS)} cached elements.")
            marked = _draw_marks(screenshot, _LAST_ELEMENTS)
            marked.save(out_path)
            return out_path, list(_LAST_ELEMENTS), screenshot.size

    uia_els = _detect_uia_elements(screenshot.size)
    text_els = _detect_text_elements(screenshot)
    elements = _merge_elements(text_els, uia_els)

    logger.info(
        f"Hybrid UIA+OCR detection: {len(uia_els)} UIA + {len(text_els)} OCR "
        f"= {len(elements)} merged elements."
    )

    with _CACHE_LOCK:
        _LAST_ELEMENTS = elements
        _LAST_SCREEN_HASH = curr_hash

    marked = _draw_marks(screenshot, elements)
    marked.save(out_path)

    return out_path, list(elements), screenshot.size


def _element_center(el):
    x1, y1, x2, y2 = el["bbox"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def _resolve_target_coords(gui_cmd, action_name):
    x = gui_cmd.get("x")
    y = gui_cmd.get("y")
    eid = gui_cmd.get("element_id")

    if (x is None or y is None) and eid is not None:
        try:
            eid = int(eid)
        except (ValueError, TypeError):
            eid = None
        if eid is not None and 1 <= eid <= len(_LAST_ELEMENTS):
            el = _LAST_ELEMENTS[eid - 1]
            x, y = _element_center(el)
            logger.info(f"Resolved element_id #{eid} '{el['text'][:40]}' -> ({x},{y})")
        else:
            return None, None, (
                f"Observation: Error -> element_id {eid} invalid. "
                f"Valid range 1-{len(_LAST_ELEMENTS)}. Call 'observe' first."
            )

    if x is None or y is None:
        return None, None, (
            f"Observation: Error -> action='{action_name}' requires either 'element_id' "
            f"OR both 'x' and 'y' as integers."
        )

    try:
        return int(x), int(y), None
    except (ValueError, TypeError):
        return None, None, "Observation: Error -> 'x' and 'y' must be valid integers."


def _normalize_label(s):
    return " ".join(str(s or "").strip().lower().split())


def _verify_expected_text(eid, expected_text):
    el = _LAST_ELEMENTS[eid - 1]
    actual = _normalize_label(el["text"])
    expected_lower = _normalize_label(expected_text)

    if not expected_lower:
        return None

    if expected_lower == actual:
        return None

    if len(expected_lower) <= 2:
        cleaned_tokens = (
            actual.replace("[", " ")
            .replace("]", " ")
            .replace("(", " ")
            .replace(")", " ")
            .replace(":", " ")
            .split()
        )
        if expected_lower in cleaned_tokens:
            return None
    else:
        if expected_lower in actual:
            return None
        if len(actual) >= 4 and len(actual) >= int(len(expected_lower) * 0.6) and actual in expected_lower:
            return None
        if difflib.SequenceMatcher(None, expected_lower, actual).ratio() >= 0.72:
            return None

    candidates = []
    for idx, e in enumerate(_LAST_ELEMENTS, 1):
        e_text = _normalize_label(e["text"])
        if not e_text:
            continue
        is_match = False
        if len(expected_lower) <= 2:
            tokens = e_text.replace("[", " ").replace("]", " ").replace("(", " ").replace(")", " ").split()
            is_match = (expected_lower == e_text) or (expected_lower in tokens)
        else:
            is_match = (
                expected_lower in e_text
                or e_text in expected_lower
                or difflib.SequenceMatcher(None, expected_lower, e_text).ratio() >= 0.65
            )
        if is_match:
            cx, cy = _element_center(e)
            candidates.append(f"#{idx} [{e.get('role', 'el')}] '{e['text'][:40]}' @({cx},{cy})")
            if len(candidates) >= 6:
                break

    hint = (
        f" Close matches: {', '.join(candidates)}."
        if candidates
        else " No close matches found."
    )

    return (
        f"Observation: Error -> element_id #{eid} actual text is '{el['text'][:50]}' "
        f"but you expected '{expected_text}'. CLICK REJECTED to prevent wrong action."
        f"{hint} Re-run 'observe' and pick the correct element_id, or verify the "
        f"'expected_text' matches the exact label shown in the observe list."
    )


def handle_gui_controller(gui_cmd: dict):
    global _LAST_ELEMENTS
    try:
        action = gui_cmd.get("action")
        wait_time = float(gui_cmd.get("wait_after_action", 0.0) or 0.0)

        if action == "observe":
            filepath, elements, (w, h) = _capture_grounded_screen()
            _LAST_ELEMENTS = elements

            with open(filepath, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            elem_lines = []
            for i, el in enumerate(elements, 1):
                cx, cy = _element_center(el)
                role = el.get("role", "text")
                text_preview = el["text"][:70].replace("\n", " ")
                elem_lines.append(f"#{i} [{role}] \"{text_preview}\" @({cx},{cy})")

            listing = (
                "\n".join(elem_lines[:_MAX_ELEMENTS])
                if elem_lines
                else "(no elements detected)"
            )

            return {
                "type": "image_payload",
                "data": [{"mime_type": "image/png", "data": img_b64}],
                "observation": (
                    f"Observation: Screen captured ({w}x{h}). "
                    f"{len(elements)} interactive elements detected and numbered "
                    f"(highlighted boxes with yellow badges).\n\n"
                    f"DETECTED ELEMENTS:\n{listing}\n\n"
                    f"WORKFLOW:\n"
                    f"1. To click any element above, call gui_controller with "
                    f"action='click_by_id', element_id=<number>, AND "
                    f"expected_text='<exact label from list>'.\n"
                    f"2. The system verifies expected_text against the actual element label. "
                    f"If they do not match, the click is REJECTED.\n"
                    f"3. For double-click use 'double_click_by_id', for right-click use "
                    f"'right_click_by_id' — always with expected_text.\n"
                    f"4. Only use raw 'click' with x,y coordinates if the target is NOT "
                    f"in the list above (e.g., canvas, image area, custom drawing).\n"
                    f"5. To type text, use action='type' with 'text' parameter. Optionally "
                    f"include 'element_id' or 'x','y' to click first. If omitted, text is "
                    f"typed into the currently focused element.\n"
                    f"6. After every action, call 'observe' again to verify the UI changed "
                    f"correctly.\n"
                    f"7. IMPORTANT: If a click response warns that the screen did NOT "
                    f"change, do NOT retry the same element_id or coordinates. Try pressing "
                    f"'enter'/'tab', or observe again and pick a different element."
                ),
            }

        if action in ["click_by_id", "double_click_by_id", "right_click_by_id"]:
            eid = gui_cmd.get("element_id")
            if eid is None:
                return "Observation: Error -> 'element_id' is required for click_by_id actions."
            try:
                eid = int(eid)
            except (ValueError, TypeError):
                return "Observation: Error -> 'element_id' must be an integer."
            if eid < 1 or eid > len(_LAST_ELEMENTS):
                return (
                    f"Observation: Error -> element_id {eid} out of range. "
                    f"Valid range: 1-{len(_LAST_ELEMENTS)}. Call 'observe' first."
                )

            expected_text = gui_cmd.get("expected_text", "")
            if expected_text:
                verify_err = _verify_expected_text(eid, str(expected_text))
                if verify_err:
                    logger.warning(
                        f"Element verification failed for #{eid}. "
                        f"Expected '{expected_text}'."
                    )
                    return verify_err

            el = _LAST_ELEMENTS[eid - 1]
            x, y = _element_center(el)

            logger.info(f"{action} -> element #{eid} '{el['text'][:50]}' at ({x},{y})")

            before_img = _capture_rgb()

            pyautogui.moveTo(x, y, duration=0.12)

            if action == "click_by_id":
                pyautogui.click()
            elif action == "double_click_by_id":
                pyautogui.doubleClick()
            elif action == "right_click_by_id":
                pyautogui.rightClick()

            _invalidate_cache()

            sleep_for = wait_time if wait_time > 0 else _DEFAULT_POST_ACTION_WAIT
            time.sleep(sleep_for)

            after_img = _capture_rgb()
            warning = ""
            if not _has_screen_changed(before_img, after_img, (x, y)):
                logger.warning(
                    f"Click on #{eid} produced no visible change."
                )
                warning = (
                    f" WARNING: Screen looks IDENTICAL after the click. The action may "
                    f"not have registered, the element may be non-interactive, or a popup "
                    f"may be blocking. DO NOT repeat the same element_id or coordinates. "
                    f"Options: (a) press 'enter' or 'tab' via 'press_key', "
                    f"(b) call 'observe' and pick a different element, "
                    f"(c) use raw 'click' with different coordinates."
                )

            return (
                f"Observation: Performed {action} on element #{eid} "
                f"'{el['text'][:50]}' at ({x},{y}).{warning} "
                f"Call 'observe' to verify the result."
            )

        if action == "type":
            text = str(gui_cmd.get("text", "") or "")
            if not text:
                return "Observation: Error -> 'type' action requires a non-empty 'text' parameter."

            x = gui_cmd.get("x")
            y = gui_cmd.get("y")
            eid = gui_cmd.get("element_id")
            clear_first = bool(gui_cmd.get("clear_first", False))
            press_enter = bool(gui_cmd.get("press_enter", False))

            if (x is None or y is None) and eid is not None:
                try:
                    eid = int(eid)
                except (ValueError, TypeError):
                    eid = None
                if eid is not None and 1 <= eid <= len(_LAST_ELEMENTS):
                    expected_text = gui_cmd.get("expected_text", "")
                    if expected_text:
                        verify_err = _verify_expected_text(eid, str(expected_text))
                        if verify_err:
                            return verify_err
                    el = _LAST_ELEMENTS[eid - 1]
                    x, y = _element_center(el)
                    logger.info(
                        f"Type target resolved from element_id #{eid} -> ({x},{y})"
                    )
                else:
                    return (
                        f"Observation: Error -> element_id {eid} invalid. "
                        f"Valid range 1-{len(_LAST_ELEMENTS)}. Call 'observe' first."
                    )

            before_img = _capture_rgb()
            target_xy = None

            if x is not None and y is not None:
                try:
                    x, y = int(x), int(y)
                except (ValueError, TypeError):
                    return "Observation: Error -> 'x' and 'y' must be valid integers."
                target_xy = (x, y)
                logger.info(f"Clicking at ({x},{y}) before typing.")
                pyautogui.moveTo(x, y, duration=0.12)
                pyautogui.click()
                time.sleep(0.18)
            else:
                logger.info("Typing directly into currently focused element.")

            if clear_first:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyautogui.press("backspace")
                time.sleep(0.06)

            if text.isascii() and "\n" not in text:
                pyautogui.write(text, interval=0.02)
            else:
                pasted = False
                try:
                    from tools.SystemTools.clipboard_tool import write_clipboard
                    if write_clipboard(text):
                        pyautogui.hotkey("ctrl", "v")
                        pasted = True
                except Exception:
                    pasted = False
                if not pasted:
                    pyautogui.write(text, interval=0.02)

            if press_enter:
                time.sleep(0.08)
                pyautogui.press("enter")

            _invalidate_cache()

            sleep_for = wait_time if wait_time > 0 else 0.35
            time.sleep(sleep_for)

            after_img = _capture_rgb()
            warning = ""
            if not _has_screen_changed(before_img, after_img, target_xy):
                logger.warning("Type action produced no visible change on screen.")
                warning = (
                    " WARNING: Screen looks IDENTICAL after typing. The text may not have "
                    "been accepted (field not focused, disabled, or the target moved). "
                    "Call 'observe' and try clicking the field again, or use 'press_key' "
                    "with 'tab' to move focus."
                )

            return (
                f"Observation: Successfully typed {len(text)} characters.{warning}"
            )

        if action in ["click", "left_click", "right_click", "double_click", "hover"]:
            x, y, err = _resolve_target_coords(gui_cmd, action)
            if err:
                return err

            logger.info(f"Executing {action} at ({x},{y})")

            before_img = _capture_rgb()

            pyautogui.moveTo(x, y, duration=0.15)

            if action in ["click", "left_click"]:
                pyautogui.click()
            elif action == "right_click":
                pyautogui.rightClick()
            elif action == "double_click":
                pyautogui.doubleClick()
            elif action == "hover":
                pass

            _invalidate_cache()

            if action == "hover":
                if wait_time > 0:
                    time.sleep(wait_time)
                return f"Observation: Successfully hovered at ({x},{y})."

            sleep_for = wait_time if wait_time > 0 else _DEFAULT_POST_ACTION_WAIT
            time.sleep(sleep_for)

            after_img = _capture_rgb()
            warning = ""
            if not _has_screen_changed(before_img, after_img, (x, y)):
                logger.warning(
                    f"Raw {action} at ({x},{y}) produced no visible change."
                )
                warning = (
                    f" WARNING: Screen looks IDENTICAL after this {action}. The target "
                    f"may not be interactive or the coordinates may be off. Try a "
                    f"different approach — call 'observe' and use 'click_by_id' with "
                    f"element_id + expected_text if the target appears in the list."
                )

            return (
                f"Observation: Performed {action} at ({x},{y}).{warning}"
            )

        elif action == "drag_and_drop":
            sx = gui_cmd.get("start_x")
            sy = gui_cmd.get("start_y")
            ex = gui_cmd.get("end_x")
            ey = gui_cmd.get("end_y")

            if None in [sx, sy, ex, ey]:
                return "Observation: Error -> drag_and_drop requires start_x, start_y, end_x, end_y."

            try:
                sx, sy, ex, ey = int(sx), int(sy), int(ex), int(ey)
            except (ValueError, TypeError):
                return "Observation: Error -> Coordinates must be valid integers."

            logger.info(f"Dragging from ({sx},{sy}) to ({ex},{ey})")
            pyautogui.moveTo(sx, sy, duration=0.15)
            pyautogui.dragTo(ex, ey, duration=0.45, button="left")

            _invalidate_cache()

            if wait_time > 0:
                time.sleep(wait_time)

            return (
                f"Observation: Successfully dragged from ({sx},{sy}) to ({ex},{ey}). "
                f"Call 'observe' to verify the result."
            )

        elif action == "press_key":
            key = gui_cmd.get("key")
            if not key:
                return "Observation: Error -> 'press_key' requires a 'key' parameter."

            logger.info(f"Pressing key: {key}")

            before_img = _capture_rgb()

            pyautogui.press(str(key))

            _invalidate_cache()

            sleep_for = wait_time if wait_time > 0 else 0.4
            time.sleep(sleep_for)

            after_img = _capture_rgb()
            warning = ""
            if not _has_screen_changed(before_img, after_img):
                logger.info(f"Key '{key}' produced no visible screen change.")
                warning = (
                    f" NOTE: Screen looks IDENTICAL after pressing '{key}'. If you "
                    f"expected a form submission or navigation, it may not have "
                    f"registered. Try a different key or click the target directly."
                )

            return f"Observation: Pressed key '{key}'.{warning}"

        elif action == "hotkey":
            keys = gui_cmd.get("keys", [])
            if not isinstance(keys, list) or not keys:
                return "Observation: Error -> 'keys' array is missing or empty."

            clean_keys = [str(k) for k in keys if k]
            if not clean_keys:
                return "Observation: Error -> 'keys' array is empty."

            logger.info(f"Pressing hotkey: {clean_keys}")

            before_img = _capture_rgb()

            pyautogui.hotkey(*clean_keys)

            _invalidate_cache()

            sleep_for = wait_time if wait_time > 0 else 0.4
            time.sleep(sleep_for)

            after_img = _capture_rgb()
            warning = ""
            if not _has_screen_changed(before_img, after_img):
                logger.info(f"Hotkey {clean_keys} produced no visible screen change.")
                warning = (
                    f" NOTE: Screen looks IDENTICAL after hotkey {clean_keys}. If a UI change "
                    f"was expected, verify the target window is focused."
                )

            return f"Observation: Pressed hotkey combo {clean_keys}.{warning}"

        elif action in ["scroll_down", "scroll_up"]:
            amount = -500 if action == "scroll_down" else 500
            logger.info(f"Scrolling screen: {action}")

            x = gui_cmd.get("x")
            y = gui_cmd.get("y")
            eid = gui_cmd.get("element_id")
            if (x is None or y is None) and eid is not None:
                try:
                    eid_int = int(eid)
                    if 1 <= eid_int <= len(_LAST_ELEMENTS):
                        x, y = _element_center(_LAST_ELEMENTS[eid_int - 1])
                except (ValueError, TypeError):
                    pass

            if x is not None and y is not None:
                try:
                    pyautogui.moveTo(int(x), int(y), duration=0.12)
                except (ValueError, TypeError):
                    pass

            pyautogui.scroll(amount)

            _invalidate_cache()

            if wait_time > 0:
                time.sleep(wait_time)
            else:
                time.sleep(0.3)

            return (
                "Observation: Scrolled screen. You MUST call 'observe' again to see "
                "the updated UI."
            )

        return f"Observation: Unknown GUI action '{action}' requested."

    except pyautogui.FailSafeException:
        logger.warning("PyAutoGUI FailSafe Triggered.")
        return (
            "Observation: Error -> Action aborted. Mouse pushed to corner "
            "triggering FailSafe."
        )
    except Exception as e:
        logger.error(f"Failed to process GUI action: {e}")
        return f"Observation: Error executing GUI action -> {e}"