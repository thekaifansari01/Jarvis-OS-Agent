import sys
import os
import json
import requests
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

def handle_protocol(url):
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        session_id = query_params.get('session_id', [None])[0]
        service = query_params.get('service', ['unknown'])[0]

        if not session_id:
            print("Error: The 'session_id' parameter is missing from the provided URL.")
            return

        api_base = os.getenv('API_BASE_URL', '').rstrip('/')
        if not api_base:
            print("Error: 'API_BASE_URL' is not configured in the environment variables.")
            return

        exchange_url = f"{api_base}/api/oauth/exchange"
        response = requests.post(
            exchange_url,
            json={'session_id': session_id},
            timeout=10
        )

        if response.status_code != 200:
            print(f"Error: Failed to exchange session ID for token. HTTP Status Code: {response.status_code}")
            print(f"Response Payload: {response.text}")
            return

        tokens = response.json()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        cookies_dir = os.path.join(base_dir, "Data", "SessionCookies")
        os.makedirs(cookies_dir, exist_ok=True)

        if service == "calendar":
            token_file = "calendar_token.json"
        else:
            token_file = "token.json"

        save_path = os.path.join(cookies_dir, token_file)

        with open(save_path, "w") as f:
            json.dump(tokens, f, indent=4)

        print(f"SUCCESS: OAuth token for '{service}' was successfully retrieved and saved.")
        print(f"File Path: {save_path}")

    except Exception as e:
        print(f"Error: An unexpected exception occurred during token processing. Details: {e}")

if __name__ == "__main__":
    print("Initializing Jarvis Protocol Handler...\n")
    if len(sys.argv) > 1:
        jarvis_url = sys.argv[1]
        handle_protocol(jarvis_url)
    else:
        print("Warning: Script was executed directly without a target URL argument.")

    input("\nPress Enter to exit...")