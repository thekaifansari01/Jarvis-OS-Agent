import os
import json
import base64
import re
import html
import time
from google.cloud import pubsub_v1

import tools.Messanger.email_manager as email_manager
from tools.Messanger.email_manager import authenticate_gmail
from Proactive.event_queue import push_proactive_event

PUBSUB_SCOPE = 'https://www.googleapis.com/auth/pubsub'
if PUBSUB_SCOPE not in email_manager.SCOPES:
    email_manager.SCOPES.append(PUBSUB_SCOPE)

base_path = os.path.dirname(os.path.abspath(__file__))
project_root = base_path
while os.path.basename(project_root) in ["tools", "Messanger", "core", "brain", "Proactive", "Email"]:
    project_root = os.path.dirname(project_root)
token_path = os.path.join(project_root, 'Data', 'SessionCookies', 'token.json')

if os.path.exists(token_path):
    try:
        with open(token_path, 'r') as f:
            token_data = json.load(f)
        if PUBSUB_SCOPE not in token_data.get('scopes', []):
            os.remove(token_path)
    except Exception:
        pass

PROJECT_ID = "jarvisemailmanager"  
TOPIC_NAME = f"projects/{PROJECT_ID}/topics/jarvis-email-topic"
SUBSCRIPTION_NAME = f"projects/{PROJECT_ID}/subscriptions/jarvis-email-sub"

def get_latest_unread_email(service, start_time_ms):
    try:
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: 
            return None, None, None, None
        
        msg_id = messages[0]['id']
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        if int(msg.get('internalDate', 0)) < start_time_ms:
            return None, None, None, None

        payload = msg.get('payload', {})
        headers = payload.get('headers', [])
        
        sender_name, sender_email, subject = "Unknown", "Unknown", "No Subject"
        for header in headers:
            if header['name'] == 'From':
                from_val = header['value']
                if '<' in from_val:
                    sender_name = from_val.split('<')[0].strip()
                    sender_email = from_val.split('<')[1].replace('>', '').strip()
                else:
                    sender_name, sender_email = from_val, from_val
            if header['name'] == 'Subject':
                subject = header['value']
                
        def decode_base64(data_str):
            try:
                data_str += "=" * ((4 - len(data_str) % 4) % 4)
                return base64.urlsafe_b64decode(data_str).decode('utf-8', errors='ignore')
            except Exception:
                return ""

        plain_text = ""
        html_text = ""

        def traverse_parts(parts):
            nonlocal plain_text, html_text
            for part in parts:
                mime_type = part.get('mimeType', '')
                data = part.get('body', {}).get('data', '')
                
                if mime_type == 'text/plain' and data:
                    plain_text += decode_base64(data) + "\n"
                elif mime_type == 'text/html' and data:
                    html_text += decode_base64(data) + "\n"
                elif 'parts' in part:
                    traverse_parts(part['parts'])

        top_mime_type = payload.get('mimeType', '')
        top_data = payload.get('body', {}).get('data', '')

        if top_mime_type == 'text/plain' and top_data:
            plain_text += decode_base64(top_data)
        elif top_mime_type == 'text/html' and top_data:
            html_text += decode_base64(top_data)
        elif 'parts' in payload:
            traverse_parts(payload['parts'])

        final_body = plain_text.strip()

        if not final_body and html_text:
            clean = re.sub(r'<style.*?>.*?</style>', '', html_text, flags=re.IGNORECASE|re.DOTALL)
            clean = re.sub(r'<script.*?>.*?</script>', '', clean, flags=re.IGNORECASE|re.DOTALL)
            clean = re.sub(r'<[^>]+>', ' ', clean)
            clean = html.unescape(clean)
            clean = re.sub(r' {2,}', ' ', clean)
            clean = re.sub(r'\n\s*\n', '\n', clean)
            final_body = clean.strip()

        if not final_body:
            final_body = msg.get('snippet', 'No readable text found in this email.')

        return sender_name, sender_email, subject, final_body
    except Exception as e:
        print(f"⚠️ Error extracting email: {e}")
        return None, None, None, None

def start_gmail_watch():
    try:
        service = authenticate_gmail()
        if not service: 
            return None
        body = {'topicName': TOPIC_NAME, 'labelIds': ['INBOX'], 'labelFilterAction': 'include'}
        response = service.users().watch(userId='me', body=body).execute()
        print(f"✅ Gmail Watch Active! History ID: {response.get('historyId')}")
        return service
    except Exception as e:
        print(f"⚠️ Watch setup failed: {e}")
        return None

def listen_for_emails():
    service = start_gmail_watch()
    if not service: 
        return

    start_time_ms = int(time.time() * 1000)
    print("🎧 Jarvis Universal Email Listener connected to Proactive Queue...")

    def process_notification(message):
        try:
            message.ack() 
            name, email, sub, body = get_latest_unread_email(service, start_time_ms)
            if name:
                print("\n" + "="*80)
                print(f"👤 Name    : {name}")
                print(f"📧 Email   : {email}")
                print(f"📌 Subject : {sub}")
                print("-" * 80)
                print(f"📝 Body    :\n{body}")
                print("="*80 + "\n")
                
                event_data = f"Email from: {name} ({email})\nSubject: {sub}\nBody: {body}"
                push_proactive_event("Gmail", event_data)
        except Exception as e:
            print(f"⚠️ Error processing notification: {e}")

    try:
        subscriber = pubsub_v1.SubscriberClient(credentials=service._http.credentials)
        streaming_pull_future = subscriber.subscribe(SUBSCRIPTION_NAME, callback=process_notification)
        with subscriber:
            streaming_pull_future.result()
    except KeyboardInterrupt:
        print("\n👋 Listener stopped.")
    except Exception as e:
        print(f"⚠️ Critical error: {e}")