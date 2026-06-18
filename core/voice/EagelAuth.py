import os
import pveagle
from dotenv import load_dotenv
from core.logger.logger import logger

load_dotenv()

class VoiceAuthenticator:
    def __init__(self):
        self.access_key = os.getenv("PICOVOICE_ACCESS_KEY")
        self.recognizer = None
        self.speaker_profile = None

        if not self.access_key:
            logger.error("PICOVOICE_ACCESS_KEY missing in .env file.")
            return

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.profile_path = os.path.join(base_dir, "Data", "UserProfile", "kaif_profile.egl")

        if not os.path.exists(self.profile_path):
            logger.error(f"Voice profile not found at: {self.profile_path}")
            return

        try:
            with open(self.profile_path, 'rb') as f:
                profile_bytes = f.read()
            
            self.speaker_profile = pveagle.EagleProfile.from_bytes(profile_bytes)
            self.recognizer = pveagle.create_recognizer(access_key=self.access_key)
            logger.info("Eagle Voice Authenticator initialized and profile loaded successfully.")
            
        except Exception as e:
            logger.error(f"Failed to initialize Eagle Authenticator: {e}")
            self.cleanup()

    def process_audio(self, all_pcm_data) -> float:
        if not self.recognizer or not self.speaker_profile:
            return 0.0

        try:
            scores = self.recognizer.process(all_pcm_data, [self.speaker_profile])
            
            if scores is None:
                return 0.0
                
            score = scores[0] if isinstance(scores, list) else scores
            return float(score) if score is not None else 0.0
            
        except pveagle.EagleActivationLimitError:
            logger.error("Picovoice free tier limit reached for Eagle!")
            self.cleanup()
            return 0.0
        except Exception as e:
            logger.error(f"Eagle processing error: {e}")
            return 0.0

    def cleanup(self):
        if self.recognizer:
            try:
                self.recognizer.delete()
            except Exception as e:
                logger.error(f"Error during Eagle cleanup: {e}")
            finally:
                self.recognizer = None