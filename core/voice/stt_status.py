import json
import logging
import zmq

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://127.0.0.1:5556")

def update_stt_status(status: str, text: str = ""):
    """Sends STT status via ZMQ instead of saving to JSON"""
    try:
        data = {"status": status, "text": text}
        socket.send_string(f"STT_UPDATE {json.dumps(data)}")
    except Exception as e:
        logging.error(f"Failed to send STT status via ZMQ: {e}")

def hide_stt_popup():
    """Forces the popup to hide by setting status to idle."""
    update_stt_status("idle", "")

def exit_stt_popup():
    """Tells the PyQt application to quit safely."""
    update_stt_status("exit", "")