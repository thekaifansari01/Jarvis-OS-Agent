import os
import cv2
import time
import requests
from dotenv import load_dotenv

load_dotenv()

FACEPP_API_KEY = os.getenv("FACEPP_API_KEY")
FACEPP_API_SECRET = os.getenv("FACEPP_API_SECRET")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFERENCE_IMAGE_PATH = os.path.join(BASE_DIR, "Data", "UserProfile", "UserFace.jpg")
LIVE_IMAGE_PATH = os.path.join(BASE_DIR, "temp_live_capture.jpg")
CONFIDENCE_THRESHOLD = 80.0

def capture_live_frame() -> bool:
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        return False

    time.sleep(1.5) 
    
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(LIVE_IMAGE_PATH, frame)
    
    cap.release()
    return ret

def verify_face_cloud() -> bool:
    if not FACEPP_API_KEY or not FACEPP_API_SECRET:
        return False

    if not os.path.exists(REFERENCE_IMAGE_PATH):
        return False

    if not os.path.exists(LIVE_IMAGE_PATH):
        return False

    url = "https://api-us.faceplusplus.com/facepp/v3/compare"
    
    data = {
        "api_key": FACEPP_API_KEY,
        "api_secret": FACEPP_API_SECRET
    }
    
    try:
        with open(REFERENCE_IMAGE_PATH, "rb") as ref_img, open(LIVE_IMAGE_PATH, "rb") as live_img:
            files = {
                "image_file1": ref_img,
                "image_file2": live_img
            }
            response = requests.post(url, data=data, files=files, timeout=10)
        
        response.raise_for_status()
        result = response.json()
        
        if "confidence" in result:
            confidence = result["confidence"]
            return confidence >= CONFIDENCE_THRESHOLD
        
        return False
            
    except Exception:
        return False
    finally:
        if os.path.exists(LIVE_IMAGE_PATH):
            try:
                os.remove(LIVE_IMAGE_PATH)
            except OSError:
                pass

def authenticate_face() -> bool:
    if capture_live_frame():
        return verify_face_cloud()
    return False