import time
import datetime
import threading
from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event
from tools.Calendar.CalendarTool import authenticate_calendar

_stop_event = threading.Event()


def stop_reminder_listener():
    _stop_event.set()


def _interruptible_sleep(seconds):
    for _ in range(int(seconds)):
        if _stop_event.is_set():
            return
        time.sleep(1)


def listen_for_reminders():
    _stop_event.clear()
    logger.info("Jarvis Universal Reminder Listener connected to Proactive Queue...")

    announced_events = set()
    ALERT_WINDOW_MINUTES = 15
    error_backoff = 60
    service = None

    while not _stop_event.is_set():
        try:
            if service is None:
                service, auth_status = authenticate_calendar(interactive=False)
                if not service:
                    logger.warning(f"Reminder Listener Error: {auth_status}")
                    _interruptible_sleep(error_backoff)
                    error_backoff = min(error_backoff * 2, 600)
                    continue
                error_backoff = 60

            now = datetime.datetime.now(datetime.timezone.utc)
            time_min = now.isoformat()
            time_max = (now + datetime.timedelta(minutes=ALERT_WINDOW_MINUTES)).isoformat()

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
                if not event_id or event_id in announced_events:
                    continue

                start_str = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Untitled Reminder')
                description = event.get('description', 'No additional details.')

                logger.info(f"Upcoming Reminder: {summary} at {start_str}")
                event_data = f"Upcoming Reminder/Event: {summary}\nStart Time: {start_str}\nDetails: {description}"
                push_proactive_event("Calendar Reminder", event_data, priority="high")
                announced_events.add(event_id)

            if len(announced_events) > 500:
                announced_events.clear()

        except Exception as e:
            logger.error(f"Unexpected error in Reminder Proactive Listener: {e}")
            service = None
            error_backoff = min(error_backoff * 2, 600)

        _interruptible_sleep(60)


if __name__ == "__main__":
    listen_for_reminders()