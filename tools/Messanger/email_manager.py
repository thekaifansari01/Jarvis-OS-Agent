import os
import time
import base64
import mimetypes
import webbrowser
from email.message import EmailMessage
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from core.brain.config import GROQ_API_KEY

try:
    from core.voice.tts import speak
except ImportError:
    def speak(text): print(f"JARVIS: {text}")

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SCOPES = ['https://mail.google.com/', 'https://www.googleapis.com/auth/pubsub']
BASE_DIR = Path(__file__).resolve().parent.parent.parent
COOKIES_DIR = BASE_DIR / "Data" / "SessionCookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_PATH = COOKIES_DIR / "token.json"

def authenticate_gmail():
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None
            try:
                TOKEN_PATH.unlink()
            except Exception:
                pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_PATH, 'w') as token:
                    token.write(creds.to_json())
            except Exception:
                creds = None
                try:
                    TOKEN_PATH.unlink()
                except Exception:
                    pass

        if not creds or not creds.valid:
            webbrowser.open("https://jarvis-oauth-server.vercel.app/api/oauth/start?service=gmail")
            timeout = 120
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if TOKEN_PATH.exists():
                    try:
                        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
                        if creds.valid:
                            break
                    except Exception:
                        pass
                time.sleep(2)

    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    return None

def send_email(to_address, subject, body, attachment_path=None):
    if attachment_path and not os.path.exists(attachment_path):
        return False

    try:
        service = authenticate_gmail()
        if not service:
            return False

        message = EmailMessage()
        message.set_content(body)
        message['To'] = to_address
        message['From'] = 'me'
        message['Subject'] = subject

        if attachment_path and os.path.exists(attachment_path):
            ctype, encoding = mimetypes.guess_type(attachment_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)

            with open(attachment_path, 'rb') as fp:
                message.add_attachment(fp.read(),
                                       maintype=maintype,
                                       subtype=subtype,
                                       filename=os.path.basename(attachment_path))

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        service.users().messages().send(userId="me", body=create_message).execute()
        return True
    except Exception:
        return False

def delete_email(query):
    try:
        service = authenticate_gmail()
        if not service:
            return False
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return False

        msg_id = messages[0]['id']
        service.users().messages().trash(userId='me', id=msg_id).execute()
        return True
    except Exception:
        return False

if __name__ == "__main__":
    auth = authenticate_gmail()