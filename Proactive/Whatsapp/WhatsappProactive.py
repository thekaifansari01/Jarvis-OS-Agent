import time
import requests
import logging
from Proactive.event_queue import push_proactive_event

def listen_for_whatsapp():
    print("🎧 Jarvis Universal WhatsApp Listener connected to Proactive Queue...")
    
    local_baileys_url = "http://localhost:3000/get-alerts"
    node_offline_logged = False

    while True:
        try:
            response = requests.get(local_baileys_url, timeout=5)
            
            if response.status_code == 200:
                node_offline_logged = False 
                data = response.json()
                alerts = data.get("alerts", [])
                
                for alert in alerts:
                    print(f"📥 [NEW WHATSAPP ALERT]: {alert}")
       
                    push_proactive_event("WhatsApp", alert, priority="high")
                    
        except requests.exceptions.ConnectionError:
            if not node_offline_logged:
                logging.warning("⚠️ Node.js Baileys server is offline. WhatsApp Proactive listener is waiting...")
                node_offline_logged = True
            time.sleep(5)
            continue
            
        except requests.exceptions.Timeout:
            pass
            
        except Exception as e:
            logging.error(f"❌ Unexpected error in WhatsApp Proactive Listener: {e}")
        
        time.sleep(2)