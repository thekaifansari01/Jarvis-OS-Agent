import time
import hashlib
import threading
import requests
from collections import deque
from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event

_stop_event = threading.Event()
_recent_alerts = deque(maxlen=500)
_recent_alerts_set = set()
_recent_lock = threading.Lock()


def stop_whatsapp_listener():
    _stop_event.set()


def _alert_hash(text):
    return hashlib.md5(text.strip().lower().encode('utf-8')).hexdigest()


def _already_seen(text):
    h = _alert_hash(text)
    with _recent_lock:
        return h in _recent_alerts_set


def _mark_seen(text):
    h = _alert_hash(text)
    with _recent_lock:
        if h in _recent_alerts_set:
            return
        if len(_recent_alerts) == _recent_alerts.maxlen:
            old = _recent_alerts[0]
            _recent_alerts_set.discard(old)
        _recent_alerts.append(h)
        _recent_alerts_set.add(h)


def listen_for_whatsapp():
    _stop_event.clear()
    logger.info("Jarvis Universal WhatsApp Listener connected to Proactive Queue...")

    local_baileys_url = "http://localhost:3000/get-alerts"
    node_offline_logged = False
    first_poll = True

    while not _stop_event.is_set():
        try:
            response = requests.get(local_baileys_url, timeout=5)

            if response.status_code == 200:
                node_offline_logged = False
                data = response.json()
                alerts = data.get("alerts", [])

                if first_poll:
                    if alerts:
                        logger.info(f"Cleared {len(alerts)} old alerts from Baileys server.")
                    first_poll = False
                    time.sleep(2)
                    continue

                for alert in alerts:
                    if _already_seen(alert):
                        continue
                    _mark_seen(alert)
                    logger.info(f"New WhatsApp Alert: {alert}")
                    push_proactive_event("WhatsApp", alert, priority="high")

        except requests.exceptions.ConnectionError:
            if not node_offline_logged:
                logger.warning("Node.js Baileys server is offline. WhatsApp Proactive listener is waiting...")
                node_offline_logged = True
            time.sleep(5)
            continue

        except requests.exceptions.Timeout:
            pass

        except Exception as e:
            logger.error(f"Unexpected error in WhatsApp Proactive Listener: {e}")

        time.sleep(2)