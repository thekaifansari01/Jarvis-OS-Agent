import time
import requests
from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event

def listen_for_whatsapp():
    logger.info("Jarvis Universal WhatsApp Listener connected to Proactive Queue...")

    local_baileys_url = "http://localhost:3000/get-alerts"
    node_offline_logged = False
    first_poll = True

    while True:
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
                    continue

                for alert in alerts:
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