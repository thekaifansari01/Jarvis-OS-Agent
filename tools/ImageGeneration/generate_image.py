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
    FAST_BRAIN_API_KEY,
    FAST_BRAIN_MODEL,
    FAST_BRAIN_ENDPOINT,
)

load_dotenv()

CREATIONS_DIR = Path.home() / "Documents" / "Jarvis" / "GeneratedImages"
CREATIONS_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_ENHANCER_SYSTEM = (
    "You are an elite AI Visual Art Director and Master Prompt Engineer. "
    "Transform the user's raw or Hinglish image request into a vivid, hyper-detailed, "
    "cinematic English image generation prompt (60 to 100 words).\n"
    "Rules:\n"
    "1. Automatically infer the best visual style (photorealistic photography, cinematic film still, "
    "cyberpunk/sci-fi, 3D Octane/Unreal Engine 5 render, anime/digital illustration, or clean vector logo/UI).\n"
    "2. Enrich with micro-details: subject textures, facial expressions or materials, environment depth, "
    "atmosphere, volumetric/cinematic lighting, color grading, and camera composition (e.g., 35mm or 85mm f/1.4 lens, "
    "shallow depth of field, ultra-sharp focus, 8k resolution).\n"
    "3. Translate any Hindi/Hinglish terms into rich visual English while preserving cultural/Indian aesthetics if implied.\n"
    "4. Strictly preserve any exact text in quotes, names, or specific colors requested by the user.\n"
    "5. Output ONLY the final enhanced prompt text. Do NOT include explanations, prefixes, labels, or surrounding quotes."
)


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")


def enhance_image_prompt(raw_prompt: str) -> str:
    clean_prompt = (raw_prompt or "").strip()
    if not clean_prompt:
        return clean_prompt

    if not FAST_BRAIN_API_KEY or not FAST_BRAIN_ENDPOINT or not FAST_BRAIN_MODEL:
        return clean_prompt

    headers = {
        "Authorization": f"Bearer {FAST_BRAIN_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": FAST_BRAIN_MODEL,
        "messages": [
            {"role": "system", "content": PROMPT_ENHANCER_SYSTEM},
            {"role": "user", "content": f"Raw image request: {clean_prompt}"},
        ],
        "temperature": 0.6,
        "max_tokens": 220,
    }

    try:
        endpoint = f"{FAST_BRAIN_ENDPOINT.rstrip('/')}/chat/completions"
        response = requests.post(endpoint, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices") or []
            if choices:
                enhanced = (choices[0].get("message", {}).get("content") or "").strip()
                enhanced = enhanced.strip("\"'")
                if len(enhanced) > 20:
                    logger.info("Enhanced image prompt: %s", enhanced)
                    return enhanced
        else:
            logger.warning("Prompt enhancer non-200 status (%s). Using raw prompt.", response.status_code)
    except Exception as e:
        logger.warning("Prompt enhancer fallback to raw prompt: %s", e)

    return clean_prompt


def generate_image_openai(prompt: str, filename: str):
    if not IMAGE_GEN_API_KEY:
        logger.error("IMAGE_GEN_API_KEY not set. Cannot generate image.")
        return "Observation: Error -> IMAGE_GEN_API_KEY missing in .env. ACTION_REQUIRED: User must add IMAGE_GEN_API_KEY to .env file, then restart Jarvis."

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
            f"{IMAGE_GEN_ENDPOINT.rstrip('/')}/images/generations",
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
                    img_response = requests.get(image_url, timeout=60)
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
            return f"Observation: Error -> Primary image API rejected request (HTTP {response.status_code}). Trying fallback provider next."
    except Exception as e:
        logger.error("Image generation error: %s", e)
        return f"Observation: Error -> Primary image API exception: {str(e)}. Trying fallback provider next."


def generate_image_horde(prompt: str, filename: str) -> str | None:
    url = "https://aihorde.net/api/v2/generate/async"
    headers = {"apikey": "0000000000", "Content-Type": "application/json"}

    logger.info("Using AI Horde for generation: %s", prompt)

    negative_prompt = (
        "blurry, low quality, lowres, distorted, grainy, deformed anatomy, disfigured, "
        "bad hands, extra fingers, missing limbs, mutated, poorly drawn face, watermark, "
        "text, signature, oversaturated, plastic skin, ugly, out of focus"
    )

    payload = {
        "prompt": f"{prompt} ### {negative_prompt}",
        "models": [AI_HORDE_IMAGE_MODEL],
        "params": {
            "steps": 30,
            "width": 1024,
            "height": 1024,
            "cfg_scale": 7.5,
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 202:
            logger.error("AI Horde generation request rejected. Status: %s", response.status_code)
            return f"Observation: Error -> AI Horde fallback rejected request (HTTP {response.status_code}). Both image providers are unavailable right now. Do NOT retry immediately."

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
        return f"Observation: Error -> AI Horde fallback failed: {str(e)}. Both image providers are unavailable. Do NOT retry."


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
        return f"Observation: Error -> AI Horde edit failed: {str(e)}. Do NOT retry."


def handle_image_command(action_type: str, prompt: str, filename: str = None, target_file: str = None):
    if not filename:
        filename = f"image_{int(time.time())}"

    if action_type == "generate":
        enhanced_prompt = enhance_image_prompt(prompt)
        result = generate_image_openai(enhanced_prompt, filename)
        if isinstance(result, str) and result.startswith("Observation: Success"):
            return result
        primary_error = result
        logger.warning("Primary image generation failed. Falling back to AI Horde.")
        result = generate_image_horde(enhanced_prompt, filename)
        if isinstance(result, str) and result.startswith("Observation: Success"):
            return result
        return f"Observation: Error -> Both image generation providers failed. Primary: {primary_error or 'unknown'}. Fallback: {result or 'unknown'}. Do NOT retry."

    if action_type == "edit":
        if not target_file:
            logger.warning("Edit command missing target file.")
            return "Observation: Error -> Edit action requires 'target_file' parameter with the absolute path of the image to edit."

        safe_target = f"{target_file}.png" if not target_file.endswith(".png") else target_file
        source_path = Path(target_file) if os.path.exists(target_file) else CREATIONS_DIR / safe_target

        if not source_path.exists():
            logger.warning("Target image not found: %s", source_path)
            return f"Observation: Error -> Source image not found at '{safe_target}'. Provide a valid absolute path."

        result = edit_via_horde(prompt, source_path, filename)
        if result is None:
            return "Observation: Error -> AI Horde edit failed. Provider unavailable. Do NOT retry."
        return result

    logger.error("Unknown image action: %s", action_type)
    return f"Observation: Error -> Unknown image action '{action_type}'. Use 'generate' or 'edit'."