import os
import json
import base64
import re
import html
import time
import threading

from tools.Messanger.email_manager import authenticate_gmail
from Proactive.event_queue import push_proactive_event
from core.logger.logger import logger

base_path = os.path.dirname(os.path.abspath(__file__))
project_root = base_path
while os.path.basename(project_root) in ["tools", "Messanger", "core", "brain", "Proactive", "Email"]:
    project_root = os.path.dirname(project_root)

session_dir = os.path.join(project_root, 'Data', 'SessionCookies')
os.makedirs(session_dir, exist_ok=True)
history_file = os.path.join(session_dir, 'gmail_history.json')

_stop_event = threading.Event()
_processed_ids = set()
_processed_ids_lock = threading.Lock()
_MAX_PROCESSED_IDS = 5000
_POLL_INTERVAL = 10
_INITIAL_BACKOFF = 10
_MAX_BACKOFF = 300


def stop_email_listener():
    _stop_event.set()


def _interruptible_sleep(seconds):
    for _ in range(int(seconds)):
        if _stop_event.is_set():
            return
        time.sleep(1)


def _load_history_id():
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                return json.load(f).get('history_id')
    except Exception:
        return None
    return None


def _save_history_id(history_id):
    try:
        with open(history_file, 'w') as f:
            json.dump({'history_id': str(history_id)}, f)
    except Exception as e:
        logger.warning(f"Failed to save Gmail history ID: {e}")


def _get_current_history_id(service):
    try:
        profile = service.users().getProfile(userId='me').execute()
        return profile.get('historyId')
    except Exception as e:
        logger.warning(f"Failed to fetch current history ID: {e}")
        return None


def decode_base64(data_str):
    try:
        data_str += "=" * ((4 - len(data_str) % 4) % 4)
        return base64.urlsafe_b64decode(data_str).decode('utf-8', errors='ignore')
    except Exception:
        return ""


def extract_email_content(service, msg_id, msg):
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

    plain_text = ""
    html_text = ""
    saved_attachments = []

    media_vault_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'Jarvis', 'MediaVault', 'Email_Attachments')
    os.makedirs(media_vault_dir, exist_ok=True)

    def download_attachment(att_id, filename):
        try:
            att_res = service.users().messages().attachments().get(
                userId='me', messageId=msg_id, id=att_id
            ).execute()
            file_data = base64.urlsafe_b64decode(att_res.get('data', '').encode('UTF-8'))
            safe_filename = re.sub(r'[^\w\-_\. ]', '_', filename)
            timestamp_str = str(int(time.time()))
            final_filename = f"{timestamp_str}_{safe_filename}"
            save_path = os.path.join(media_vault_dir, final_filename)
            with open(save_path, "wb") as f:
                f.write(file_data)
            saved_attachments.append(os.path.abspath(save_path).replace("\\", "/"))
        except Exception as e:
            logger.warning(f"Attachment download error: {e}")

    def traverse_parts(parts):
        nonlocal plain_text, html_text
        for part in parts:
            mime_type = part.get('mimeType', '')
            data = part.get('body', {}).get('data', '')
            filename = part.get('filename', '')
            att_id = part.get('body', {}).get('attachmentId', '')

            if filename and att_id:
                download_attachment(att_id, filename)
            elif mime_type == 'text/plain' and data and not filename:
                plain_text += decode_base64(data) + "\n"
            elif mime_type == 'text/html' and data and not filename:
                html_text += decode_base64(data) + "\n"
            elif 'parts' in part:
                traverse_parts(part['parts'])

    top_mime_type = payload.get('mimeType', '')
    top_data = payload.get('body', {}).get('data', '')
    top_filename = payload.get('filename', '')
    top_att_id = payload.get('body', {}).get('attachmentId', '')

    if top_filename and top_att_id:
        download_attachment(top_att_id, top_filename)
    elif top_mime_type == 'text/plain' and top_data:
        plain_text += decode_base64(top_data)
    elif top_mime_type == 'text/html' and top_data:
        html_text += decode_base64(top_data)
    elif 'parts' in payload:
        traverse_parts(payload['parts'])

    final_body = plain_text.strip()
    if not final_body and html_text:
        clean = re.sub(r'<style.*?>.*?</style>', '', html_text, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r'<script.*?>.*?</script>', '', clean, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = html.unescape(clean)
        clean = re.sub(r' {2,}', ' ', clean)
        clean = re.sub(r'\n\s*\n', '\n', clean)
        final_body = clean.strip()
    if not final_body:
        final_body = msg.get('snippet', 'No readable text found in this email.')

    return sender_name, sender_email, subject, final_body, saved_attachments, msg_id


def get_all_unread_emails(service, start_time_ms, max_results=25):
    try:
        results = service.users().messages().list(
            userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results
        ).execute()
        messages = results.get('messages', [])
        emails = []
        for msg in messages:
            msg_id = msg['id']
            full_msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            internal_date = int(full_msg.get('internalDate', 0))
            if internal_date < start_time_ms:
                continue
            name, email, sub, body, saved_attachments, msg_id = extract_email_content(service, msg_id, full_msg)
            emails.append((name, email, sub, body, saved_attachments, msg_id))
        return emails
    except Exception as e:
        logger.warning(f"Error fetching unread emails: {e}")
        return []


def mark_as_read(service, msg_id):
    try:
        service.users().messages().modify(
            userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to mark email {msg_id} as read: {e}")


def _cleanup_processed_ids():
    global _processed_ids
    with _processed_ids_lock:
        if len(_processed_ids) > _MAX_PROCESSED_IDS:
            _processed_ids = set(list(_processed_ids)[-_MAX_PROCESSED_IDS // 2:])


def _process_message(service, msg_id, start_time_ms):
    with _processed_ids_lock:
        if msg_id in _processed_ids:
            return
        _processed_ids.add(msg_id)

    try:
        full_msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    except Exception as e:
        logger.warning(f"Failed to fetch message {msg_id}: {e}")
        return

    labels = full_msg.get('labelIds', [])
    if 'INBOX' not in labels or 'UNREAD' not in labels:
        return

    internal_date = int(full_msg.get('internalDate', 0))
    if internal_date < start_time_ms:
        return

    try:
        name, email, sub, body, saved_attachments, _ = extract_email_content(service, msg_id, full_msg)
    except Exception as e:
        logger.warning(f"Failed to extract email content for {msg_id}: {e}")
        return

    logger.info(f"Email from: {name} ({email}) | Subject: {sub}")
    if saved_attachments:
        logger.info(f"Attachments: {', '.join(saved_attachments)}")

    event_data = f"Email from: {name} ({email})\nSubject: {sub}\nBody: {body}"
    if saved_attachments:
        att_str = ", ".join(saved_attachments)
        event_data += f"\n[Attachments Saved]: {att_str}"

    push_proactive_event("Gmail", event_data)
    mark_as_read(service, msg_id)


def _poll_history(service, state):
    current_history_id = state.get('history_id')

    if not current_history_id:
        new_id = _get_current_history_id(service)
        if new_id:
            state['history_id'] = str(new_id)
            _save_history_id(new_id)
        return

    try:
        response = service.users().history().list(
            userId='me',
            startHistoryId=str(current_history_id),
            historyTypes=['messageAdded']
        ).execute()
    except Exception as e:
        err_str = str(e).lower()
        if '404' in err_str or 'not found' in err_str or 'starthistoryid' in err_str:
            logger.warning("Gmail history ID expired. Resetting baseline.")
            new_id = _get_current_history_id(service)
            if new_id:
                state['history_id'] = str(new_id)
                _save_history_id(new_id)
            return
        raise

    message_ids = []
    for record in response.get('history', []):
        for added in record.get('messagesAdded', []):
            msg = added.get('message', {})
            mid = msg.get('id')
            labels = msg.get('labelIds', [])
            if not mid:
                continue
            if 'INBOX' not in labels:
                continue
            if 'UNREAD' not in labels:
                continue
            if mid not in message_ids:
                message_ids.append(mid)

    for mid in message_ids:
        if _stop_event.is_set():
            return
        try:
            _process_message(service, mid, state['start_time_ms'])
        except Exception as e:
            logger.warning(f"Failed to process message {mid}: {e}")

    new_history_id = response.get('historyId')
    if new_history_id and str(new_history_id) != str(current_history_id):
        state['history_id'] = str(new_history_id)
        _save_history_id(new_history_id)

    _cleanup_processed_ids()


def listen_for_emails():
    _stop_event.clear()

    service = authenticate_gmail(interactive=False)
    if not service:
        logger.warning("Email listener: Gmail authentication failed. Listener not started.")
        return

    state = {
        'history_id': _load_history_id(),
        'start_time_ms': int(time.time() * 1000)
    }

    if not state['history_id']:
        initial_id = _get_current_history_id(service)
        if initial_id:
            state['history_id'] = str(initial_id)
            _save_history_id(initial_id)

    logger.info("Jarvis Universal Email Listener connected to Proactive Queue...")

    backoff = _INITIAL_BACKOFF

    while not _stop_event.is_set():
        try:
            _poll_history(service, state)
            backoff = _INITIAL_BACKOFF
        except Exception as e:
            logger.warning(f"Email polling error: {e}")
            _interruptible_sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
            continue

        _interruptible_sleep(_POLL_INTERVAL)

    logger.info("Email listener stopped.")