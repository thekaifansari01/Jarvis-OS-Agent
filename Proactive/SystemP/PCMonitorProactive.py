import os
import time
import threading
import socket
import ctypes
import re
from ctypes import wintypes
from typing import Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

try:
    import win32evtlog
except ImportError:
    win32evtlog = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

from core.logger.logger import logger
from Proactive.event_queue import push_proactive_event

COOLDOWN_SECONDS = 60
IDLE_THRESHOLD_SECONDS = 600
DISK_THRESHOLD_GB = 5.0
CPU_THRESHOLD = 85.0
RAM_THRESHOLD = 85.0
BATTERY_LOW_THRESHOLD = 15.0

_stop_event = threading.Event()
_last_alert_times: Dict[str, float] = {}
_JARVIS_PID: Optional[int] = None
_PID_LOAD_TIME: float = 0

def _load_jarvis_pid(force: bool = False):
    global _JARVIS_PID, _PID_LOAD_TIME
    current_time = time.time()
    if not force and (current_time - _PID_LOAD_TIME) < 10:
        return
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lock_path = os.path.join(root_dir, ".jarvis.lock")
        if os.path.exists(lock_path):
            with open(lock_path, "r") as f:
                content = f.read().strip()
                if content.isdigit():
                    new_pid = int(content)
                    if _JARVIS_PID != new_pid:
                        _JARVIS_PID = new_pid
                        logger.debug(f"Loaded Jarvis PID: {_JARVIS_PID}")
                    _PID_LOAD_TIME = current_time
                    return
        if _JARVIS_PID is not None:
            logger.debug("Jarvis lock file missing, clearing cached PID")
        _JARVIS_PID = None
        _PID_LOAD_TIME = current_time
    except Exception as e:
        logger.debug(f"Failed to load Jarvis PID: {e}")
        _JARVIS_PID = None
        _PID_LOAD_TIME = current_time

def _extract_pid(proc_string: str) -> Optional[int]:
    if not proc_string:
        return None
    match = re.search(r'\(PID:\s*(\d+)\)', proc_string)
    if match:
        return int(match.group(1))
    return None

def _is_jarvis_process(pid: int) -> bool:
    if psutil is None:
        return False
    _load_jarvis_pid()
    if _JARVIS_PID is None:
        return False
    if pid == _JARVIS_PID:
        return True
    try:
        parent = psutil.Process(pid).ppid()
        if parent == _JARVIS_PID:
            return True
    except Exception:
        pass
    return False

def get_idle_time_seconds() -> float:
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
        lastInputInfo = LASTINPUTINFO()
        lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo)):
            millis = ctypes.windll.kernel32.GetTickCount() - lastInputInfo.dwTime
            return millis / 1000.0
    except Exception:
        pass
    return 0.0

def is_fullscreen_app_active() -> bool:
    if not gw:
        return False
    try:
        active_win = gw.getActiveWindow()
        if active_win:
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            if active_win.width >= screen_w and active_win.height >= screen_h:
                return True
    except Exception:
        pass
    return False

def get_top_cpu_process() -> str:
    try:
        if psutil is None:
            return "Unknown (psutil missing)"
        top_proc = max(psutil.process_iter(['pid', 'name', 'cpu_percent']),
                       key=lambda p: p.info.get('cpu_percent', 0) or 0)
        return f"{top_proc.info.get('name', 'Unknown')} (PID: {top_proc.info.get('pid', '?')})"
    except Exception:
        return "Unknown"

def get_top_memory_process() -> str:
    try:
        if psutil is None:
            return "Unknown (psutil missing)"
        top_proc = max(psutil.process_iter(['pid', 'name', 'memory_percent']),
                       key=lambda p: p.info.get('memory_percent', 0) or 0)
        return f"{top_proc.info.get('name', 'Unknown')} (PID: {top_proc.info.get('pid', '?')})"
    except Exception:
        return "Unknown"

def check_internet_connectivity(host="8.8.8.8", port=53, timeout=3) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

def get_new_usb_devices():
    if not win32evtlog:
        return []
    new_devices = []
    try:
        hand = win32evtlog.OpenEventLog(None, "System")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        current_time = time.time()
        for event in events:
            if (current_time - event.TimeGenerated.timestamp()) > 15:
                break
            if event.EventID in [2003, 2100, 24577]:
                for string in event.StringInserts:
                    if string and ('USB' in string or 'Device' in string):
                        event_key = f"usb_{event.EventID}_{string[:20]}"
                        last_time = _last_alert_times.get(event_key, 0)
                        if time.time() - last_time > 300:
                            new_devices.append(string)
                            _last_alert_times[event_key] = time.time()
                        break
        win32evtlog.CloseEventLog(hand)
    except Exception as e:
        logger.debug(f"USB Event Log read error: {e}")
    return new_devices

def should_send_alert(alert_key: str) -> bool:
    try:
        last_time = _last_alert_times.get(alert_key, 0)
        if time.time() - last_time < COOLDOWN_SECONDS:
            return False
        _last_alert_times[alert_key] = time.time()
        return True
    except Exception:
        return False

def build_event_data(alert_type: str, details: str, priority: str = "normal") -> str:
    return f"Source: PC_Monitor\nType: {alert_type}\nPriority: {priority}\n{details}"

def monitor_system_resources():
    if psutil is None:
        return

    try:
        cpu = psutil.cpu_percent(interval=1)
        if cpu > CPU_THRESHOLD:
            proc = get_top_cpu_process()
            pid = _extract_pid(proc)
            if pid is not None and _is_jarvis_process(pid):
                logger.debug("CPU alert skipped: process belongs to Jarvis (self or child)")
            else:
                details = f"CPU usage is at {cpu:.1f}% (Threshold: {CPU_THRESHOLD}%)\nTop Process: {proc}"
                if should_send_alert("cpu_high"):
                    push_proactive_event("PC_Monitor", build_event_data("Resource_Alert", details, "high"))
    except Exception as e:
        logger.debug(f"CPU monitor error: {e}")

    try:
        mem = psutil.virtual_memory()
        if mem.percent > RAM_THRESHOLD:
            proc = get_top_memory_process()
            pid = _extract_pid(proc)
            if pid is not None and _is_jarvis_process(pid):
                logger.debug("RAM alert skipped: process belongs to Jarvis (self or child)")
            else:
                details = f"RAM usage is at {mem.percent:.1f}% ({mem.used // (1024**3)} GB / {mem.total // (1024**3)} GB)\nTop Process: {proc}"
                if should_send_alert("ram_high"):
                    push_proactive_event("PC_Monitor", build_event_data("Resource_Alert", details, "high"))
    except Exception as e:
        logger.debug(f"RAM monitor error: {e}")

    try:
        disk = psutil.disk_usage('/')
        free_gb = disk.free / (1024**3)
        if free_gb < DISK_THRESHOLD_GB:
            details = f"Low Disk Space! Only {free_gb:.1f} GB free on C: drive."
            if should_send_alert("disk_low"):
                push_proactive_event("PC_Monitor", build_event_data("Storage_Alert", details, "high"))
    except Exception as e:
        logger.debug(f"Disk monitor error: {e}")

def monitor_battery():
    if psutil is None:
        return
    try:
        battery = psutil.sensors_battery()
        if not battery:
            return
        percent = battery.percent
        is_plugged = battery.power_plugged
        if percent < BATTERY_LOW_THRESHOLD and not is_plugged:
            details = f"Battery is critically low at {percent}%. Please plug in the charger."
            if should_send_alert("battery_low"):
                push_proactive_event("PC_Monitor", build_event_data("Battery_Alert", details, "critical"))
        status_key = "charging" if is_plugged else "discharging"
        if should_send_alert(f"power_{status_key}"):
            details = f"Power status changed: {'Charging' if is_plugged else 'On Battery'} ({percent}%)"
            push_proactive_event("PC_Monitor", build_event_data("System_Event", details, "normal"))
    except Exception as e:
        logger.debug(f"Battery monitor error: {e}")

def monitor_network():
    try:
        if not check_internet_connectivity():
            if should_send_alert("network_down"):
                push_proactive_event("PC_Monitor", build_event_data("Network_Alert", "Internet connection lost!", "high"))
    except Exception as e:
        logger.debug(f"Network monitor error: {e}")

def listen_for_pc_monitor():
    if psutil is None:
        logger.error("psutil not installed. PC Monitor cannot start.")
        return

    _load_jarvis_pid(force=True)
    logger.info("PC Monitor connected to Proactive Queue...")
    _last_alert_times.clear()

    while not _stop_event.is_set():
        try:
            idle_time = get_idle_time_seconds()
            fullscreen = is_fullscreen_app_active()
            is_user_away = (idle_time > IDLE_THRESHOLD_SECONDS) or fullscreen

            if not is_user_away:
                monitor_system_resources()
            else:
                if should_send_alert("user_away_heartbeat"):
                    logger.debug("PC Monitor: User idle/fullscreen. Resource alerts suppressed.")

            monitor_battery()
            monitor_network()

            if win32evtlog:
                for device in get_new_usb_devices():
                    details = f"New USB Device detected: {device}"
                    push_proactive_event("PC_Monitor", build_event_data("Hardware_Alert", details, "normal"))

            time.sleep(5)

        except Exception as e:
            logger.error(f"PC Monitor loop error: {e}")
            time.sleep(10)

def stop_pc_monitor():
    _stop_event.set()