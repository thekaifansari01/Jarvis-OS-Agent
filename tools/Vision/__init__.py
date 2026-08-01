import os
import base64
from typing import List
from core.logger.logger import logger
from core.brain.config import get_model_capabilities, AGENT_PRIMARY_PROVIDER

def encode_image_to_base64(file_path: str) -> str:
    with open(file_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def inspect_media_files(file_paths: List[str], query: str) -> str:
    if not file_paths or not query:
        return "Observation: Error -> Both 'file_paths' and 'query' are required for inspect_media."

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
        from google import genai
        from google.genai import types
        import os as sys_os
        
        gemini_client = genai.Client(api_key=sys_os.getenv("GEMINI_API_KEY"))
        
        contents_payload = []
        for path in valid_paths:
            ext = path.split('.')[-1].lower()
            mime_type = "image/jpeg"
            if ext == "png": mime_type = "image/png"
            elif ext == "webp": mime_type = "image/webp"
            elif ext == "pdf": mime_type = "application/pdf"
            
            b64_data = encode_image_to_base64(path)
            contents_payload.append(
                types.Part.from_bytes(data=base64.b64decode(b64_data), mime_type=mime_type)
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

    except Exception as e:
        logger.error(f"❌ Media Inspection failed: {e}")
        return f"Observation: Error during media inspection -> {str(e)}"