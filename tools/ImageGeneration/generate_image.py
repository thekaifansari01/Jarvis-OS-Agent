import os
import time
import base64
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image
from dotenv import load_dotenv

from core.logger.logger import logger
from core.voice.tts import speak
from core.brain.config import (
    IMAGE_GEN_API_KEY,
    IMAGE_GEN_MODEL,
    IMAGE_GEN_ENDPOINT,
    AI_HORDE_IMAGE_MODEL,
)

load_dotenv()

CREATIONS_DIR = Path.home() / "Documents" / "Jarvis" / "GeneratedImages"
CREATIONS_DIR.mkdir(parents=True, exist_ok=True)


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")


def generate_image_openai(prompt: str, filename: str) -> str | None:
    if not IMAGE_GEN_API_KEY:
        logger.error("IMAGE_GEN_API_KEY not set. Cannot generate image.")
        return None

    headers = {
        "Authorization": f"Bearer {IMAGE_GEN_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": IMAGE_GEN_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }

    try:
        response = requests.post(
            f"{IMAGE_GEN_ENDPOINT}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                image_b64 = data["data"][0].get("b64_json")
                if image_b64:
                    image_data = base64.b64decode(image_b64)
                    img = Image.open(BytesIO(image_data))
                else:
                    image_url = data["data"][0].get("url")
                    if not image_url:
                        logger.error("No image data or URL in response.")
                        return None
                    img_response = requests.get(image_url)
                    img = Image.open(BytesIO(img_response.content))

                safe_filename = f"{filename}.png" if not filename.endswith(".png") else filename
                save_path = CREATIONS_DIR / safe_filename
                img.save(save_path)
                img.show()
                logger.info("Image generated and saved at: %s", save_path)
                speak("Sir, image generate ho gayi hai. Aap screen par dekh sakte hain.")
                return str(save_path.resolve())
        else:
            logger.error("Image generation API error: %s - %s", response.status_code, response.text)
            return None
    except Exception as e:
        logger.error("Image generation error: %s", e)
        return None


def generate_image_horde(prompt: str, filename: str) -> str | None:
    url = "https://aihorde.net/api/v2/generate/async"
    headers = {"apikey": "0000000000", "Content-Type": "application/json"}

    logger.info("Using AI Horde for generation: %s", prompt)

    payload = {
        "prompt": f"{prompt} ### blurry, low quality, distorted, grainy",
        "models": [AI_HORDE_IMAGE_MODEL],
        "params": {
            "steps": 25,
            "width": 1024,
            "height": 1024,
            "cfg_scale": 7,
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 202:
            logger.error("AI Horde generation request rejected. Status: %s", response.status_code)
            return None

        task_id = response.json().get("id")
        status_url = f"https://aihorde.net/api/v2/generate/status/{task_id}"
        first_notified = False

        while True:
            time.sleep(4)
            try:
                status_res = requests.get(status_url).json()
            except Exception:
                continue

            if status_res.get("done"):
                img_url = status_res["generations"][0]["img"]
                img_res = requests.get(img_url)
                img = Image.open(BytesIO(img_res.content))

                safe_filename = f"{filename}.png" if not filename.endswith(".png") else filename
                save_path = CREATIONS_DIR / safe_filename
                img.save(save_path)
                img.show()
                logger.info("AI Horde generation saved at: %s", save_path)
                speak("Sir, image backup server se generate ho gayi hai.")
                return str(save_path.resolve())

            wait_time = status_res.get("wait_time", 0)
            if not first_notified and wait_time > 0:
                minutes = wait_time // 60
                seconds = wait_time % 60
                if minutes > 0 and seconds > 0:
                    time_str = f"{minutes} minute aur {seconds} second"
                elif minutes > 0:
                    time_str = f"{minutes} minute"
                else:
                    time_str = f"{seconds} second"
                speak(f"Sir, image generate hone mein lagbhag {time_str} lagenge. Main background mein kaam kar raha hoon.")
                first_notified = True

    except Exception as e:
        logger.error("AI Horde generation error: %s", e)
        return None


def edit_via_horde(prompt: str, source_image_path: str, new_filename: str) -> str | None:
    url = "https://aihorde.net/api/v2/generate/async"
    headers = {"apikey": "0000000000", "Content-Type": "application/json"}

    logger.info("Editing image via AI Horde: %s", prompt)

    payload = {
        "prompt": f"{prompt} ### blurry, low quality, distorted, grainy",
        "source_image": image_to_base64(source_image_path),
        "source_processing": "img2img",
        "models": [AI_HORDE_IMAGE_MODEL],
        "params": {
            "steps": 25,
            "width": 1024,
            "height": 1024,
            "denoising_strength": 0.65,
            "cfg_scale": 7,
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 202:
            logger.error("AI Horde edit request rejected. Status: %s", response.status_code)
            return None

        task_id = response.json().get("id")
        status_url = f"https://aihorde.net/api/v2/generate/status/{task_id}"
        first_notified = False

        while True:
            time.sleep(4)
            try:
                status_res = requests.get(status_url).json()
            except Exception:
                continue

            if status_res.get("done"):
                img_url = status_res["generations"][0]["img"]
                img_res = requests.get(img_url)
                img = Image.open(BytesIO(img_res.content))

                safe_filename = f"{new_filename}.png" if not new_filename.endswith(".png") else new_filename
                save_path = CREATIONS_DIR / safe_filename
                img.save(save_path)
                img.show()
                logger.info("Editing complete. Saved at: %s", save_path)
                speak("Sir, image successfully edit ho gayi hai. Aap screen par dekh sakte hain.")
                return str(save_path.resolve())

            wait_time = status_res.get("wait_time", 0)
            if not first_notified and wait_time > 0:
                minutes = wait_time // 60
                seconds = wait_time % 60
                if minutes > 0 and seconds > 0:
                    time_str = f"{minutes} minute aur {seconds} second"
                elif minutes > 0:
                    time_str = f"{minutes} minute"
                else:
                    time_str = f"{seconds} second"
                speak(f"Sir, image edit karne mein lagbhag {time_str} lagenge. Main background mein kaam kar raha hoon.")
                first_notified = True

    except Exception as e:
        logger.error("Horde edit error: %s", e)
        return None


def handle_image_command(action_type: str, prompt: str, filename: str = None, target_file: str = None) -> str | None:
    if not filename:
        filename = f"image_{int(time.time())}"

    if action_type == "generate":
        result = generate_image_openai(prompt, filename)
        if not result:
            logger.warning("Primary image generation failed. Falling back to AI Horde.")
            result = generate_image_horde(prompt, filename)
        return result

    if action_type == "edit":
        if not target_file:
            logger.warning("Edit command missing target file.")
            speak("Sir, mujhe samajh nahi aaya ki konsi image edit karni hai. Kripya naam batayein.")
            return None

        safe_target = f"{target_file}.png" if not target_file.endswith(".png") else target_file
        source_path = Path(target_file) if os.path.exists(target_file) else CREATIONS_DIR / safe_target

        if not source_path.exists():
            logger.warning("Target image not found: %s", source_path)
            speak(f"Sir, mujhe '{safe_target}' naam ki koi image nahi mili.")
            return None

        return edit_via_horde(prompt, source_path, filename)

    logger.error("Unknown image action: %s", action_type)
    return None