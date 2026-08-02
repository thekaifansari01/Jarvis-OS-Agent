import os
import base64
from typing import List, Union, Dict, Any
from core.logger.logger import logger

# Direct imports - jo already config mein define hain
from core.brain.config import (
    AGENT_PRIMARY_PROVIDER,
    GEMINI_AGENT_MODEL,
    REGOLO_MODEL,
    OPENROUTER_MODEL
)

def encode_image_to_base64(file_path: str) -> str:
    """Encode image file to base64 string."""
    with open(file_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_current_model():
    """Get the current model config object based on primary provider"""
    if AGENT_PRIMARY_PROVIDER == "gemini":
        return GEMINI_AGENT_MODEL
    elif AGENT_PRIMARY_PROVIDER == "regolo":
        return REGOLO_MODEL
    elif AGENT_PRIMARY_PROVIDER == "openrouter":
        return OPENROUTER_MODEL
    else:
        return None

def inspect_media_files(file_paths: List[str], query: str, has_vision: bool = None) -> Union[str, Dict[str, Any]]:
    """
    Inspect media files (images/videos) using vision capabilities.
    
    Args:
        file_paths: List of absolute local file paths to inspect
        query: Question or instruction about the media
        has_vision: Boolean indicating if provider has vision capability.
                   If None, auto-detect from config.
    
    Returns:
        Observation string or image payload dict for inline processing
    """
    if not file_paths or not query:
        return "Observation: Error -> Both 'file_paths' and 'query' are required for vision tool."

    # Auto-detect vision capability from config models
    if has_vision is None:
        current_model = get_current_model()
        if current_model:
            # Directly use the vision attribute from ModelConfig
            has_vision = getattr(current_model, 'vision', False)
            logger.info(f"👁️ Auto-detected vision capability: {has_vision} from {AGENT_PRIMARY_PROVIDER}")
        else:
            has_vision = False
            logger.warning(f"⚠️ Unknown provider: {AGENT_PRIMARY_PROVIDER}, vision disabled")

    valid_paths = []
    for path in file_paths:
        clean_path = os.path.abspath(path.replace("\\", "/"))
        if os.path.exists(clean_path) and os.access(clean_path, os.R_OK):
            valid_paths.append(clean_path)
        else:
            logger.warning(f"⚠️ Media file not found or unreadable: {clean_path}")

    if not valid_paths:
        return "Observation: Error -> None of the provided file paths exist or are readable on the system."

    logger.info(f"👁️ Inspecting {len(valid_paths)} media file(s) for query: '{query}'")

    try:
        if has_vision:
            # Only include images for inline payload
            image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
            image_paths = [p for p in valid_paths if os.path.splitext(p)[1].lower() in image_extensions]
            
            if not image_paths:
                return "Observation: Error -> Only image files (JPG, PNG, WEBP, GIF) are supported for inline vision. Please provide image files or use a different provider."
            
            image_payloads = []
            for path in image_paths:
                ext = os.path.splitext(path)[1].lower()
                mime_type = "image/jpeg"
                if ext == ".png":
                    mime_type = "image/png"
                elif ext == ".webp":
                    mime_type = "image/webp"
                elif ext == ".gif":
                    mime_type = "image/gif"
                
                b64_data = encode_image_to_base64(path)
                image_payloads.append({
                    "mime_type": mime_type,
                    "data": b64_data,
                    "path": path
                })
            
            return {
                "type": "image_payload",
                "data": image_payloads,
                "query": query,
                "observation": f"Observation: [Media Loaded Inline] -> Successfully loaded {len(image_paths)} image(s) for direct inspection."
            }

        # Fallback: Direct Gemini API call (for providers without vision)
        try:
            from google import genai
            from google.genai import types
            from dotenv import load_dotenv
            import os as sys_os
            
            load_dotenv()
            gemini_key = sys_os.getenv("GEMINI_API_KEY")
            
            if not gemini_key:
                return "Observation: Error -> GEMINI_API_KEY not found. Please set it in .env file."
            
            gemini_client = genai.Client(api_key=gemini_key)
            
            contents_payload = []
            for path in valid_paths:
                ext = os.path.splitext(path)[1].lower()
                mime_type = "image/jpeg"
                if ext == ".png":
                    mime_type = "image/png"
                elif ext == ".webp":
                    mime_type = "image/webp"
                elif ext == ".gif":
                    mime_type = "image/gif"
                elif ext == ".pdf":
                    mime_type = "application/pdf"
                elif ext in [".mp4", ".avi", ".mov", ".mkv"]:
                    mime_type = "video/mp4"
                
                with open(path, "rb") as f:
                    file_data = f.read()
                    contents_payload.append(
                        types.Part.from_bytes(data=file_data, mime_type=mime_type)
                    )

            contents_payload.append(query)

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents_payload,
                config=types.GenerateContentConfig(temperature=0.1)
            )

            answer = response.text.strip() if response.text else "No observation generated."
            logger.info("✅ Media inspection complete.")
            return f"Observation: [Media Analysis Result] -> {answer}"

        except ImportError as e:
            logger.error(f"❌ Google GenAI import error: {e}")
            return f"Observation: Error -> Google GenAI library not installed. Run: pip install google-genai"
        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}")
            return f"Observation: Error -> Gemini API call failed: {str(e)}"

    except Exception as e:
        logger.error(f"❌ Media Inspection failed: {e}")
        return f"Observation: Error during media inspection -> {str(e)}"