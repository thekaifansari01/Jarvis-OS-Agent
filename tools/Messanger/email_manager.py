import os
import time
import base64
import mimetypes
from email.message import EmailMessage
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

from core.brain.config import GROQ_EMAIL_SUMMARY_MODEL, EMAIL_SUMMARY_MAX_TOKENS, GROQ_API_KEY

try:
    from core.voice.tts import speak
except ImportError:
    def speak(text): print(f"🔊 JARVIS SAYS: {text}")

START_TIMESTAMP = int(time.time())

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SCOPES = ['https://mail.google.com/']

def authenticate_gmail():
    """Google API connection with credentials inside Data/SessionCookies folder."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    if "tools" in base_path or "core" in base_path:
        project_root = base_path
        while os.path.basename(project_root) in ["tools", "Messanger", "core", "brain"]:
            project_root = os.path.dirname(project_root)
        session_folder = os.path.join(project_root, 'Data', 'SessionCookies')
    else:
        session_folder = os.path.join(base_path, 'Data', 'SessionCookies')
    
    os.makedirs(session_folder, exist_ok=True)
    
    credentials_path = os.path.join(session_folder, 'credentials.json')
    token_path = os.path.join(session_folder, 'token.json')

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("🔄 Token successfully refreshed.")
            except Exception as e:
                print(f"⚠️ Token refresh failed (might be revoked). Generating a new one... Error: {e}")
                creds = None
        
        if not creds or not creds.valid:
            print(f"🔐 Gmail Access: Using {credentials_path}")
            if not os.path.exists(credentials_path):
                print(f"❌ Error: credentials.json nahi mili is path par: {credentials_path}")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def send_email(to_address, subject, body, attachment_path=None):
    """Jarvis ke through kisi ko email bhejna, ab attachments ke saath."""
    
    if attachment_path and not os.path.exists(attachment_path):
        print(f"❌ Attachment file missing: {attachment_path}")
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
            print(f"📎 Attached file: {os.path.basename(attachment_path)}")

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        send_message = service.users().messages().send(userId="me", body=create_message).execute()
        print(f"✅ Email sent successfully to {to_address}! ID: {send_message['id']}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to send email: {e}")
        return False

def delete_email(query):
    try:
        service = authenticate_gmail()
        if not service:
            return False
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print("😶 Koi matching email nahi mila delete karne ke liye.")
            return False

        msg_id = messages[0]['id']
        service.users().messages().trash(userId='me', id=msg_id).execute()
        print(f"🗑️ Email successfully moved to Trash. (Query: {query})")
        return True
    except Exception as e:
        print(f"⚠️ Error deleting email: {e}")
        return False

def check_new_emails(event_queue=None):
    """
    Background poller: Checks for new emails and pushes RAW data 
    to the Proactive Queue only if they arrived AFTER the script started.
    """
    try:
        service = authenticate_gmail()
        if not service:
            return
            
        days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y/%m/%d')
        query = f"is:unread after:{days_ago}"
        
        results = service.users().messages().list(userId='me', q=query, labelIds=['INBOX']).execute()
        messages = results.get('messages', [])

        if not messages:
            return

        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            
            msg_timestamp = int(msg_data.get('internalDate', 0)) / 1000
            
            if msg_timestamp <= START_TIMESTAMP:
                continue

            headers = msg_data['payload']['headers']
            subject = "No Subject"
            sender = "Unknown"
            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                if header['name'] == 'From':
                    sender = header['value']
            
            snippet = msg_data.get('snippet', '')
            clean_sender = sender.split('<')[0].strip()
            
            alert_text = f"[SYSTEM ALERT]: Ek naya email aaya hai. From: {clean_sender}, Subject: {subject}, Body: {snippet}. Isko padh kar user ko naturally short mein batao."
            
            print(f"📧 [{datetime.now().strftime('%I:%M %p')}] New live mail detected from {clean_sender}!")
            print(f"📥 Queuing Proactive Alert: Mail from {clean_sender}")
            
            if event_queue is not None:
                event_queue.put(alert_text)

            service.users().messages().modify(userId='me', id=msg['id'], body={'removeLabelIds': ['UNREAD']}).execute()
            time.sleep(1)
            
    except Exception as e:
        print(f"⚠️ Gmail Error: {e}")

if __name__ == "__main__":
    print("Testing Gmail Authentication path configurations...")
    auth = authenticate_gmail()
    if auth:
        print("✅ Path configuration successfully validated!")