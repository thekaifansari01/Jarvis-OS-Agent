import queue
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

@dataclass
class ProactiveEvent:
    source: str
    data: str
    priority: str = "normal"
    timestamp: datetime = field(default_factory=datetime.now)

_proactive_queue = queue.Queue()
_agent_task_queue = queue.Queue()

def push_proactive_event(source: str, data: str, priority: str = "normal"):
    event = ProactiveEvent(source=source, data=data, priority=priority)
    _proactive_queue.put(event)

def get_proactive_event() -> ProactiveEvent:
    try:
        return _proactive_queue.get_nowait()
    except queue.Empty:
        return None

def get_batched_events(window_seconds: int = 4) -> List[ProactiveEvent]:
    try:
        first_event = _proactive_queue.get(timeout=1.0)
    except queue.Empty:
        return []
        
    events = [first_event]
    
    if first_event.priority == "high":
        return events
        
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        remaining = window_seconds - elapsed
        
        if remaining <= 0:
            break
            
        try:
            next_event = _proactive_queue.get(timeout=remaining)
            events.append(next_event)
            if next_event.priority == "high":
                break
        except queue.Empty:
            break
            
    return events