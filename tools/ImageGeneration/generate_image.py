import os
import time
import base64
import json
import requests
from PIL import Image
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
from core.logger.logger import logger
from core.voice.tts import speak

from core.brain.config import (
    REGOLO_API_KEY,
    REGOLO_BASE_URL,
    AI_HORDE_IMAGE_MODEL
)

load_dotenv()

CREATIONS_DIR = Path.home() / "Documents" / "Jarvis" / "GeneratedImages"
CREATIONS_DIR.mkdir(parents=True, exist_ok=True)
REGOLO_IMAGE_MODEL = "Qwen-Image"


def image_to_base64(image_path):
    """Convert image to base64 string for AI Horde."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')


def generate_image_regolo(prompt: str, filename: str) -> str:
    """
    Generate image using Regolo.ai Qwen-Image-2512 model.
    """
    if not REGOLO_API_KEY:
        logger.error("REGOLO_API_KEY not found! Please add to .env")
        return None

    logger.info(f"🎨 Jarvis generating image with Regolo Qwen-Image-2512: {prompt}")

    try:
        headers = {
            "Authorization": f"Bearer {REGOLO_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": REGOLO_IMAGE_MODEL,
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1,
            "response_format": "b64_json"  
        }

        response = requests.post(
            f"{REGOLO_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code == 200:
            data = response.json()

            if data.get("data") and len(data["data"]) > 0:
                image_b64 = data["data"][0].get("b64_json")
                if image_b64:
                    image_data = base64.b64decode(image_b64)
                    img = Image.open(BytesIO(image_data))

                    safe_filename = f"{filename}.png" if not filename.endswith(".png") else filename
                    save_path = CREATIONS_DIR / safe_filename

                    img.save(save_path)
                    img.show()

                    logger.info(f"✅ Image generated and saved at: {save_path}")
                    speak("Sir, image generate ho gayi hai. Aap screen par dekh sakte hain.")
                    return str(save_path.resolve())
                else:
                    image_url = data["data"][0].get("url")
                    if image_url:
                        img_response = requests.get(image_url)
                        img = Image.open(BytesIO(img_response.content))
                        safe_filename = f"{filename}.png" if not filename.endswith(".png") else filename
                        save_path = CREATIONS_DIR / safe_filename
                        img.save(save_path)
                        img.show()
                        logger.info(f"✅ Image generated and saved at: {save_path}")
                        return str(save_path.resolve())
            else:
                logger.error(f"❌ No image data in response: {data}")
                return None
        else:
            logger.error(f"❌ Regolo API Error: {response.status_code} - {response.text}")
            return None

    except requests.exceptions.Timeout:
        logger.error("❌ Regolo API timeout after 120 seconds")
        speak("Sir, image generation mein time lag raha hai. Please try again.")
        return None
    except Exception as e:
        logger.error(f"❌ Regolo Image Generation Error: {e}")
        return None


def edit_via_horde(prompt, source_image_path, new_filename):
    """
    Edit image using AI Horde (img2img).
    """
    url = "https://aihorde.net/api/v2/generate/async"
    headers = {"apikey": "0000000000", "Content-Type": "application/json"}

    logger.info(f"🎨 Jarvis is EDITING image via AI Horde: {prompt}")

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
            "cfg_scale": 7
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 202:
            logger.error("AI Horde server rejected the request.")
            return None

        task_id = response.json().get("id")
        status_url = f"https://aihorde.net/api/v2/generate/status/{task_id}"

        first_time_notified = False

        while True:
            time.sleep(4)
            try:
                status_res = requests.get(status_url).json()
            except:
                continue

            if status_res.get("done"):
                img_url = status_res["generations"][0]["img"]
                img_res = requests.get(img_url)
                img = Image.open(BytesIO(img_res.content))

                safe_filename = f"{new_filename}.png" if not new_filename.endswith(".png") else new_filename
                save_path = CREATIONS_DIR / safe_filename

                img.save(save_path)
                print("\n")
                img.show()

                success_msg = "Sir, image successfully edit ho gayi hai. Aap screen par dekh sakte hain."
                logger.info(f"✅ Editing Complete! Saved at: {save_path}")
                speak(success_msg)

                return str(save_path.resolve())

            wait_time = status_res.get('wait_time', 0)

            if not first_time_notified and wait_time > 0:
                minutes = wait_time // 60
                seconds = wait_time % 60

                if minutes > 0 and seconds > 0:
                    time_str = f"{minutes} minute aur {seconds} second"
                elif minutes > 0 and seconds == 0:
                    time_str = f"{minutes} minute"
                else:
                    time_str = f"{seconds} second"

                notification = f"Sir, image ko edit karne mein lagbhag {time_str} lagenge. Main background mein kaam kar raha hoon."
                speak(notification)
                first_time_notified = True

    except Exception as e:
        print("\n")
        logger.error(f"❌ Horde Error: {e}")
        return None


def generate_flux_fallback(prompt, filename):
    """
    Fallback: Generate using Together AI FLUX (if Regolo fails).
    """
    try:
        from together import Together
        from core.brain.config import FLUX_IMAGE_MODEL, TOGETHER_API_KEY

        if not TOGETHER_API_KEY:
            logger.warning("TOGETHER_API_KEY not found, skipping fallback.")
            return None

        together_client = Together(api_key=TOGETHER_API_KEY)
        logger.info(f"🔄 Falling back to FLUX for image generation: {prompt}")

        response = together_client.images.generate(
            model=FLUX_IMAGE_MODEL,
            prompt=prompt,
            steps=4,
            response_format="b64_json"
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        img = Image.open(BytesIO(image_data))

        safe_filename = f"{filename}.png" if not filename.endswith(".png") else filename
        save_path = CREATIONS_DIR / safe_filename

        img.save(save_path)
        img.show()

        logger.info(f"✅ FLUX fallback completed! Saved at: {save_path}")
        speak("Sir, image backup server se generate ho gayi hai.")
        return str(save_path.resolve())
    except Exception as e:
        logger.error(f"❌ FLUX fallback error: {e}")
        return None


def handle_image_command(action_type, prompt, filename=None, target_file=None):
    if not filename:
        filename = f"image_{int(time.time())}"

    if action_type == "generate":
        result = generate_image_regolo(prompt, filename)

        if not result:
            logger.warning("⚠️ Regolo generation failed. Trying FLUX fallback...")
            result = generate_flux_fallback(prompt, filename)

        return result

    elif action_type == "edit":
        if not target_file:
            logger.warning("Edit karne ke liye target_file ka naam nahi mila.")
            speak("Sir, mujhe samajh nahi aaya ki konsi image edit karni hai. Kripya naam batayein.")
            return None

        safe_target = f"{target_file}.png" if not target_file.endswith(".png") else target_file
        source_image_path = Path(target_file) if os.path.exists(target_file) else CREATIONS_DIR / safe_target

        if not source_image_path.exists():
            logger.warning(f"File nahi mili: {source_image_path}")
            speak(f"Sir, mujhe '{safe_target}' naam ki koi image nahi mili.")
            return None

        return edit_via_horde(prompt, source_image_path, filename)

    else:
        logger.error(f"Unknown image action: {action_type}")
        return None