import os
import datetime
import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
COOKIES_DIR = BASE_DIR / "Data" / "SessionCookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

CREDS_PATH = COOKIES_DIR / "credentials.json"
TOKEN_PATH = COOKIES_DIR / "calendar_token.json"

SCOPES = ['https://www.googleapis.com/auth/calendar']
DEFAULT_TIMEZONE = 'Asia/Kolkata'

def helper_format_to_iso(time_str: str, default_time_suffix: str = "00:00:00") -> str:
    """
    Agent ke simple input (e.g., '2026-05-27 15:30:00' ya '2026-05-27')
    ko strict Google-compliant ISO 8601 format mein convert karta hai.
    """
    if not time_str:
        return ""
    
    time_str = time_str.strip()
    
    if "T" in time_str and ("+" in time_str or "Z" in time_str):
        return time_str
        
    try:
        if len(time_str) == 10:
            time_str = f"{time_str} {default_time_suffix}"
            
        dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime('%Y-%m-%dT%H:%M:%S+05:30')
    except Exception as e:
        logging.error(f"Time parsing failed for '{time_str}': {e}")
        return ""

def authenticate_calendar():
    """Google Calendar ke credentials fetch aur refresh karta hai."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.warning(f"Token refresh failed: {e}. Re-authenticating...")
                creds = None
                
        if not creds:
            if not CREDS_PATH.exists():
                return None, f"Observation: Error -> Credentials file not found at {CREDS_PATH}. Admin needs to add it."
            
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds), "Success"

def create_event(summary: str, start_time: str, end_time: str, description: str = "") -> str:
    """Naya event/reminder create karta hai."""
    service, auth_status = authenticate_calendar()
    if not service:
        return auth_status

    start_iso = helper_format_to_iso(start_time, "00:00:00")
    end_iso = helper_format_to_iso(end_time, "23:59:59")

    if not start_iso or not end_iso:
        return "Observation: Error -> Invalid time format provided. Use 'YYYY-MM-DD HH:MM:SS' format."

    try:
        event_body = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_iso, 'timeZone': DEFAULT_TIMEZONE},
            'end': {'dateTime': end_iso, 'timeZone': DEFAULT_TIMEZONE},
            'reminders': {
                'useDefault': False,
                'overrides': [{'method': 'popup', 'minutes': 15}],
            },
        }
        
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return f"Observation: Success -> Event '{summary}' scheduled successfully. Event ID: '{event.get('id')}'."
        
    except Exception as e:
        return f"Observation: API Error while creating event -> {e}"

def check_events(start_time: str = None, end_time: str = None, max_results: int = 10) -> str:
    """Specific time range ke events fetch karta hai aur unique ID bhi deta hai."""
    service, auth_status = authenticate_calendar()
    if not service:
        return auth_status

    if not start_time:
        start_iso = datetime.datetime.utcnow().isoformat() + 'Z'
    else:
        start_iso = helper_format_to_iso(start_time, "00:00:00")
        
    end_iso = helper_format_to_iso(end_time, "23:59:59") if end_time else None

    try:
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=start_iso,
            timeMax=end_iso,
            maxResults=max_results, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return "Observation: Is time range mein calendar mein koi event ya reminder schedule nahi hai. User ko bolo ki wo free hai."
        
        output = "Observation: Found these scheduled events. Use the exact Event ID if you need to delete any:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            title = event.get('summary', 'Untitled Event')
            e_id = event.get('id')
            output += f"- Event: '{title}' | ID: '{e_id}' | Time: {start}\n"
            
        return output
        
    except Exception as e:
        return f"Observation: API Error while fetching events -> {e}"

def delete_event(event_id: str = None, summary_query: str = None) -> str:
    """
    Event delete karne ki advanced capability.
    ID se direct delete karega, ya title match karke dhoondega.
    """
    service, auth_status = authenticate_calendar()
    if not service:
        return auth_status

    if not event_id and not summary_query:
        return "Observation: Error -> Deletion requires either an 'event_id' or a 'summary_query'."

    try:
        if event_id:
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            return f"Observation: Success -> Event with ID '{event_id}' has been deleted successfully."

        if summary_query:
            logging.info(f"Searching for event matching query: '{summary_query}' to delete...")
            now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
                calendarId='primary', timeMin=now_iso, maxResults=50, singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            target_id = None
            matched_title = ""

            for event in events:
                title = event.get('summary', '').lower()
                if summary_query.lower() in title:
                    target_id = event.get('id')
                    matched_title = event.get('summary')
                    break

            if target_id:
                service.events().delete(calendarId='primary', eventId=target_id).execute()
                return f"Observation: Success -> Found and deleted the event '{matched_title}' (ID: {target_id}) successfully."
            else:
                return f"Observation: Error -> '{summary_query}' naam ka koi bhi event aane wale dino mein nahi mila. User se bolo ki sahi naam batayein."

    except Exception as e:
        return f"Observation: API Error while deleting event -> {e}"

if __name__ == '__main__':
    print("==================================================")
    print("🧪 STARTING ADVANCED LIFECYCLE TESTING")
    print("==================================================\n")

    print("🟢 STEP 1: Creating a dynamic test event...")
    test_title = "Jarvis Advanced Deletion Test"
    fake_start = "2026-05-28 16:00:00"
    fake_end = "2026-05-28 16:30:00"
    
    create_res = create_event(test_title, fake_start, fake_end, "Testing delete flows.")
    print(create_res)
    print("-" * 50)

    print("\n🟢 STEP 2: Checking events to verify creation and fetch ID...")
    check_res = check_events("2026-05-28 00:00:00", "2026-05-28 23:59:59")
    print(check_res)
    print("-" * 50)

    print("\n🟢 STEP 3: Simulating deletion via Title Query ('Advanced Deletion Test')...")
    delete_res = delete_event(summary_query="Advanced Deletion Test")
    print(delete_res)
    print("-" * 50)

    print("\n🟢 STEP 4: Final verification check...")
    final_check = check_events("2026-05-28 00:00:00", "2026-05-28 23:59:59")
    print(final_check)
    print("==================================================")