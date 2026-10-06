# core/utils/shutdown.py

import threading

_shutdown_event = threading.Event()

def set_shutdown():
    _shutdown_event.set()

def is_shutdown():
    return _shutdown_event.is_set()

def clear_shutdown():
    _shutdown_event.clear()