import queue

_proactive_queue = queue.Queue()

def push_proactive_event(source: str, data: str):
    _proactive_queue.put({"source": source, "data": data})

def get_proactive_event():
    try:
        return _proactive_queue.get_nowait()
    except queue.Empty:
        return None