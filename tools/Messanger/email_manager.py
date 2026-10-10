import os
import time
import base64
import mimetypes
import webbrowser
import json
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from core.logger.logger import logger
from core.security import load_decrypted_token, save_encrypted_token

try:
    from core.voice.tts import speak
except ImportError:
    def speak(text):
        logger.warning(f"TTS not available, speaking via log: {text}")

load_dotenv()

SCOPES = ['https://mail.google.com/', 'https://www.googleapis.com/auth/pubsub']
BASE_DIR = Path(__file__).resolve().parent.parent.parent
COOKIES_DIR = BASE_DIR / "Data" / "SessionCookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_PATH = COOKIES_DIR / "token.enc"


def authenticate_gmail(interactive: bool = True):
    logger.info("🔐 Authenticating Gmail...")
    creds = None
    if TOKEN_PATH.exists():
        try:
            token_info = load_decrypted_token(str(TOKEN_PATH))
            if token_info:
                creds = Credentials.from_authorized_user_info(token_info, SCOPES)
                logger.debug("✅ Gmail token found.")
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
                save_encrypted_token(json.loads(creds.to_json()), str(TOKEN_PATH))
                logger.info("🔄 Gmail token refreshed.")
            except Exception:
                creds = None
                try:
                    TOKEN_PATH.unlink()
                except Exception:
                    pass

        if (not creds or not creds.valid) and interactive:
            import uuid
            secure_session = str(uuid.uuid4())
            logger.info("🌐 Opening browser for Gmail OAuth...")
            webbrowser.open(f"https://jarvis-os-agent.vercel.app/api/oauth/start?service=gmail&state={secure_session}")
            timeout = 120
            start_time = time.time()
            while time.time() - start_time < timeout:
                if TOKEN_PATH.exists():
                    try:
                        token_info = load_decrypted_token(str(TOKEN_PATH))
                        if token_info:
                            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
                            if creds and creds.valid:
                                logger.info("✅ Gmail OAuth completed.")
                                break
                    except Exception:
                        pass
                time.sleep(3)

    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds, cache_discovery=False)
    logger.error("❌ Gmail authentication failed.")
    return None


def send_email(to_address, subject, body, attachment_path=None):
    logger.info(f"📧 Sending email to {to_address} | Subject: {subject}")
    if attachment_path and not os.path.exists(attachment_path):
        logger.warning(f"Attachment not found: {attachment_path}")
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
        logger.info(f"✅ Email sent successfully to {to_address}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}")
        return False


def delete_email(query):
    logger.info(f"🗑️ Attempting to delete email with query: {query}")
    try:
        service = authenticate_gmail()
        if not service:
            return False
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            logger.warning(f"No email found for query: {query}")
            return False

        msg_id = messages[0]['id']
        service.users().messages().trash(userId='me', id=msg_id).execute()
        logger.info(f"✅ Email deleted (trashed) with ID: {msg_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to delete email: {e}")
        return False


def _load_email_helpers():
    try:
        from Proactive.Email.EmailProactive import extract_email_content, mark_as_read as _mark_as_read
        return extract_email_content, _mark_as_read
    except ImportError:
        try:
            from Proactive.Email.EmailProactive import extract_email_content, mark_as_read as _mark_as_read
            return extract_email_content, _mark_as_read
        except ImportError as imp_err:
            logger.error(f"❌ EmailProactive helpers could not be imported: {imp_err}")
            return None, None


def fetch_emails_by_date(start_date, end_date=None, query=None, max_results=50, mark_as_read_flag=False):
    extract_email_content, _mark_as_read = _load_email_helpers()
    if not extract_email_content or not _mark_as_read:
        return {
            "success": False,
            "error": "Email fetch helpers unavailable. Check Proactive module path.",
            "count": 0,
            "emails": [],
            "saved_attachments": []
        }

    service = authenticate_gmail(interactive=False)
    if not service:
        return {
            "success": False,
            "error": "Gmail authentication failed.",
            "count": 0,
            "emails": [],
            "saved_attachments": []
        }

    try:
        start_dt = datetime.strptime(str(start_date).strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": f"Invalid start_date '{start_date}'. Expected format YYYY-MM-DD.",
            "count": 0,
            "emails": [],
            "saved_attachments": []
        }

    if end_date:
        try:
            end_dt = datetime.strptime(str(end_date).strip(), "%Y-%m-%d")
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid end_date '{end_date}'. Expected format YYYY-MM-DD.",
                "count": 0,
                "emails": [],
                "saved_attachments": []
            }
    else:
        end_dt = start_dt

    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    before_dt = end_dt + timedelta(days=1)
    gmail_query = f"after:{start_dt.strftime('%Y/%m/%d')} before:{before_dt.strftime('%Y/%m/%d')}"

    if query and str(query).strip():
        gmail_query = f"{gmail_query} {str(query).strip()}"

    try:
        max_results = int(max_results)
    except (ValueError, TypeError):
        max_results = 50

    if max_results <= 0:
        max_results = 10000
    max_results = min(max_results, 10000)

    all_emails = []
    all_attachments = []
    page_token = None
    remaining = max_results
    MAX_PER_PAGE = 500

    logger.info(f"📬 Fetching emails | query='{gmail_query}' | max={max_results}")

    try:
        while remaining > 0:
            fetch_count = min(remaining, MAX_PER_PAGE)
            list_params = {
                "userId": "me",
                "q": gmail_query,
                "maxResults": fetch_count
            }
            if page_token:
                list_params["pageToken"] = page_token

            results = service.users().messages().list(**list_params).execute()
            messages = results.get("messages", [])

            if not messages:
                break

            for msg_ref in messages:
                msg_id = msg_ref.get("id")
                if not msg_id:
                    continue

                try:
                    full_msg = service.users().messages().get(
                        userId="me", id=msg_id, format="full"
                    ).execute()

                    name, email, sub, body, saved_attachments, _ = extract_email_content(
                        service, msg_id, full_msg
                    )

                    internal_date = int(full_msg.get("internalDate", 0))
                    try:
                        date_str = datetime.fromtimestamp(internal_date / 1000).strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, OSError, OverflowError):
                        date_str = "Unknown"

                    all_emails.append({
                        "from_name": name,
                        "from_email": email,
                        "subject": sub,
                        "body": body,
                        "date": date_str,
                        "attachments": list(saved_attachments) if saved_attachments else [],
                        "msg_id": msg_id
                    })

                    if saved_attachments:
                        all_attachments.extend(saved_attachments)

                    if mark_as_read_flag:
                        try:
                            _mark_as_read(service, msg_id)
                        except Exception as mark_err:
                            logger.warning(f"Failed to mark {msg_id} as read: {mark_err}")

                except Exception as msg_err:
                    logger.warning(f"Failed to fetch message {msg_id}: {msg_err}")
                    continue

            remaining -= len(messages)
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"✅ Fetch complete | count={len(all_emails)} | attachments={len(all_attachments)}")

        return {
            "success": True,
            "count": len(all_emails),
            "emails": all_emails,
            "saved_attachments": all_attachments,
            "date_range": {
                "start": start_dt.strftime("%Y-%m-%d"),
                "end": end_dt.strftime("%Y-%m-%d")
            }
        }

    except Exception as e:
        logger.error(f"❌ Failed to fetch emails: {e}")
        return {
            "success": False,
            "error": str(e),
            "count": len(all_emails),
            "emails": all_emails,
            "saved_attachments": all_attachments
        }


if __name__ == "__main__":
    auth = authenticate_gmail()