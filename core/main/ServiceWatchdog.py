import time
import logging
import threading
from core.main.BackgroundServices import (
    start_baileys_server,
    start_stt_popup,
    is_baileys_running,
    is_stt_popup_running
)

class ServiceWatchdog:
    def __init__(self, check_interval=5, max_retries=3, cooldown=15):
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.cooldown = cooldown
        self._is_running = False
        self._thread = None
        
        self.services = {
            "baileys": {
                "is_running_check": is_baileys_running,
                "start_func": start_baileys_server,
                "retries": 0,
                "last_restart": 0
            },
            "stt_popup": {
                "is_running_check": is_stt_popup_running,
                "start_func": start_stt_popup,
                "retries": 0,
                "last_restart": 0
            }
        }

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logging.info("Service Watchdog started.")

    def stop(self):
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logging.info("Service Watchdog stopped.")

    def _monitor_loop(self):
        time.sleep(10) 
        
        while self._is_running:
            current_time = time.time()
            
            for service_name, service_data in self.services.items():
                if not self._is_running:
                    break

                if current_time - service_data["last_restart"] < self.cooldown:
                    continue

                try:
                    is_active = service_data["is_running_check"]()
                    
                    if not is_active:
                        if service_data["retries"] >= self.max_retries:
                            logging.error(f"Watchdog: {service_name} exceeded maximum retries. Abandoning restart.")
                            continue

                        logging.warning(f"Watchdog: {service_name} process down. Attempting restart {service_data['retries'] + 1}/{self.max_retries}.")
                        
                        service_data["start_func"]()
                        service_data["retries"] += 1
                        service_data["last_restart"] = current_time
                        
                    else:
                        if current_time - service_data["last_restart"] > (self.cooldown * 2):
                            service_data["retries"] = 0

                except Exception as e:
                    logging.error(f"Watchdog error monitoring {service_name}: {e}")

            time.sleep(self.check_interval)

watchdog_instance = ServiceWatchdog()

def start_watchdog():
    watchdog_instance.start()

def stop_watchdog():
    watchdog_instance.stop()