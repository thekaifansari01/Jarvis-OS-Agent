import time
import logging
import datetime
from Proactive.event_queue import push_proactive_event
from tools.Calendar.CalendarTool import authenticate_calendar

def listen_for_reminders():
    print("🎧 Jarvis Universal Reminder Listener connected to Proactive Queue...")
    announced_events = set()
    ALERT_WINDOW_MINUTES = 15
    while True:
        try:
            service, auth_status = authenticate_calendar(interactive=False)
            if not service:
                logging.warning(f"⚠️ Reminder Listener Error: {auth_status}")
                time.sleep(60)
                continue
            now = datetime.datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + datetime.timedelta(minutes=ALERT_WINDOW_MINUTES)).isoformat() + 'Z'
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            for event in events:
                event_id = event.get('id')
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Untitled Reminder')
                description = event.get('description', 'No additional details.')
                if event_id not in announced_events:
                    print(f"⏰ [UPCOMING REMINDER]: {summary} at {start_str}")
                    event_data = f"Upcoming Reminder/Event: {summary}\nStart Time: {start_str}\nDetails: {description}"
                    push_proactive_event("Calendar Reminder", event_data, priority="high")
                    announced_events.add(event_id)
            if len(announced_events) > 500:
                announced_events.clear()
        except Exception as e:
            logging.error(f"❌ Unexpected error in Reminder Proactive Listener: {e}")
        time.sleep(60)

if __name__ == "__main__":
    listen_for_reminders()