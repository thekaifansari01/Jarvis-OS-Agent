import queue
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ProactiveEvent:
    source: str
    data: str
    priority: str = "normal"
    timestamp: datetime = field(default_factory=datetime.now)

_proactive_queue = queue.Queue()

def push_proactive_event(source: str, data: str, priority: str = "normal"):
    event = ProactiveEvent(source=source, data=data, priority=priority)
    _proactive_queue.put(event)

def get_proactive_event() -> ProactiveEvent:
    try:
        return _proactive_queue.get_nowait()
    except queue.Empty:
        return None