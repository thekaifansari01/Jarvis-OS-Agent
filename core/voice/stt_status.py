import json
import logging
import socket

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
UDP_IP = "127.0.0.1"
UDP_PORT = 5556

def update_stt_status(status: str, text: str = ""):
    """Sends STT status via UDP instead of ZMQ"""
    try:
        data = {"status": status, "text": text}
        json_data = json.dumps(data).encode('utf-8')
        udp_socket.sendto(json_data, (UDP_IP, UDP_PORT))
    except Exception as e:
        logging.error(f"Failed to send STT status via UDP: {e}")

def hide_stt_popup():
    """Forces the popup to hide by setting status to idle."""
    update_stt_status("idle", "")

def exit_stt_popup():
    """Tells the PyQt application to quit safely."""
    update_stt_status("exit", "")