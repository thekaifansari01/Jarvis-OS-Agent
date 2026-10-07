"""
STTPopup Test Script
--------------------
Ye script STTPopup.py ko test karne ke liye UDP messages bhejti hai.
Pehle STTPopup.py chalao, phir ye script chalao.

Usage:
    Terminal 1: python SttPopup.py
    Terminal 2: python test_stt_popup.py
"""

import socket
import json
import time
import sys

UDP_IP = "127.0.0.1"
UDP_PORT = 5556

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send(data: dict):
    """UDP packet bhejo STTPopup ko"""
    message = json.dumps(data).encode("utf-8")
    sock.sendto(message, (UDP_IP, UDP_PORT))
    print(f"  → Sent: {data}")


def wait(seconds):
    time.sleep(seconds)


def test_listening_partial():
    """Test 1: Listening state with partial text building up"""
    print("\n=== TEST 1: Listening (partial text) ===")
    send({"status": "listening", "text": ""})
    wait(0.5)
    send({"status": "listening", "text": "hello"})
    wait(0.4)
    send({"status": "listening", "text": "hello world"})
    wait(0.4)
    send({"status": "listening", "text": "hello world how are you"})
    wait(1.0)


def test_understanding():
    """Test 2: Understanding state (processing)"""
    print("\n=== TEST 2: Understanding ===")
    send({"status": "understanding", "text": "hello world how are you"})
    wait(1.5)


def test_transcribed():
    """Test 3: Transcribed (success) - green border"""
    print("\n=== TEST 3: Transcribed ===")
    send({"status": "transcribed", "text": "Hello world, how are you?"})
    wait(3.0)  # transcribed_timer is 2s


def test_hindi():
    """Test 4: Hindi text"""
    print("\n=== TEST 4: Hindi text ===")
    send({"status": "listening", "text": "नमस्ते"})
    wait(0.5)
    send({"status": "listening", "text": "नमस्ते दुनिया"})
    wait(0.5)
    send({"status": "understanding", "text": "नमस्ते दुनिया"})
    wait(1.0)
    send({"status": "transcribed", "text": "नमस्ते दुनिया, आप कैसे हैं?"})
    wait(3.0)


def test_long_text():
    """Test 5: Long text (max width 800)"""
    print("\n=== TEST 5: Long text ===")
    long_text = ("This is a very long transcription text to test how the popup "
                 "handles width constraints and text truncation when the content "
                 "exceeds the maximum allowed width of the island.")
    send({"status": "listening", "text": ""})
    wait(0.5)
    send({"status": "listening", "text": long_text})
    wait(1.0)
    send({"status": "transcribed", "text": long_text})
    wait(3.0)


def test_idle():
    """Test 6: Idle - should hide popup"""
    print("\n=== TEST 6: Idle (should hide) ===")
    send({"status": "idle", "text": ""})
    wait(1.0)


def test_rapid_updates():
    """Test 7: Rapid text updates (simulates fast streaming)"""
    print("\n=== TEST 7: Rapid streaming updates ===")
    words = ["The", "The quick", "The quick brown", "The quick brown fox",
             "The quick brown fox jumps", "The quick brown fox jumps over",
             "The quick brown fox jumps over the", "The quick brown fox jumps over the lazy dog"]
    for w in words:
        send({"status": "listening", "text": w})
        wait(0.15)
    wait(0.5)
    send({"status": "understanding", "text": words[-1]})
    wait(1.0)
    send({"status": "transcribed", "text": words[-1] + "."})
    wait(3.0)


def test_full_cycle():
    """Test 8: Complete cycle - idle → listening → understanding → transcribed → idle"""
    print("\n=== TEST 8: Full cycle ===")
    send({"status": "listening", "text": ""})
    wait(1.0)
    send({"status": "listening", "text": "testing full cycle"})
    wait(1.0)
    send({"status": "understanding", "text": "testing full cycle"})
    wait(1.5)
    send({"status": "transcribed", "text": "Testing full cycle."})
    wait(3.0)
    send({"status": "idle", "text": ""})
    wait(1.0)


def test_invalid_data():
    """Test 9: Invalid/malformed data (should not crash)"""
    print("\n=== TEST 9: Invalid data (robustness) ===")
    # Invalid JSON
    sock.sendto(b"not json at all", (UDP_IP, UDP_PORT))
    print("  → Sent raw bytes (invalid JSON)")
    wait(0.3)
    # Missing fields
    send({"foo": "bar"})
    wait(0.3)
    # Empty dict
    send({})
    wait(0.3)
    # Unknown status
    send({"status": "unknown_state", "text": "test"})
    wait(1.0)


def test_exit():
    """Test 10: Exit command (last test - quits app)"""
    print("\n=== TEST 10: Exit command ===")
    send({"status": "exit", "text": ""})
    wait(0.5)


def main():
    if len(sys.argv) > 1:
        # Specific test chalao by name
        test_name = sys.argv[1]
        tests = {
            "1": test_listening_partial,
            "2": test_understanding,
            "3": test_transcribed,
            "4": test_hindi,
            "5": test_long_text,
            "6": test_idle,
            "7": test_rapid_updates,
            "8": test_full_cycle,
            "9": test_invalid_data,
            "10": test_exit,
        }
        if test_name in tests:
            tests[test_name]()
        else:
            print(f"Unknown test: {test_name}")
            print("Available: 1-10")
        return

    # Default: saare tests chalao (exit ke bina)
    print("=" * 60)
    print("STTPopup Test Suite")
    print("=" * 60)
    print(f"Target: {UDP_IP}:{UDP_PORT}")
    print("Make sure SttPopup.py is running in another terminal!")
    print("Starting in 2 seconds...")
    time.sleep(2)

    test_listening_partial()
    test_understanding()
    test_transcribed()
    test_hindi()
    test_long_text()
    test_idle()
    test_rapid_updates()
    test_full_cycle()
    test_invalid_data()
    test_exit()

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()