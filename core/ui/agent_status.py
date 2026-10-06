import json
from datetime import datetime
import zmq

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://127.0.0.1:5555")

def reset_agent_status():
    """Boot time par call karna taaki purana stuck status clear ho jaye"""
    status = {
        "timestamp": datetime.now().isoformat(),
        "step": 0,
        "total_steps": 0,
        "tokens": 0,  
        "thought": "System Initialized...",
        "action": "idle",
        "action_detail": "",
        "observation": ""
    }
    
    socket.send_string(f"AGENT_UPDATE {json.dumps(status)}")

def update_agent_status(
    step: int, 
    total_steps: int, 
    thought: str, 
    action: str = "", 
    action_detail: str = "", 
    observation: str = "", 
    tokens: int = 0  # 
):
    """Call this inside agent loop to update UI instantly via ZMQ"""
    status = {
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "total_steps": total_steps,
        "tokens": tokens,  
        "thought": thought,
        "action": action,
        "action_detail": action_detail,
        "observation": observation[:200]
    }
    
    socket.send_string(f"AGENT_UPDATE {json.dumps(status)}")