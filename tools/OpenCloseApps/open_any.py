import webbrowser
from AppOpener import open as open_app

APP_PATHS = {}

WEB_URLS = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chat.openai.com",
}

def open_any_app(apps_to_open, silent=False):
    """
    Jarvis-level App Opener using AppOpener.
    Opens local apps natively, and falls back to web URLs if the app is missing (Great for LTSC).
    """
    opened = []
    failed = []
    
    if isinstance(apps_to_open, str):
        apps_to_open = [apps_to_open]

    for name in apps_to_open:
        name_lower = name.lower().strip()

        if name_lower in WEB_URLS:
            print(f"🌐 Jarvis: Opening '{name}' in browser...")
            webbrowser.open(WEB_URLS[name_lower])
            opened.append(f"{name} (web)")
            continue

        print(f"🔄 Jarvis: Attempting to open local app '{name}'...")
        try:
            open_app(name_lower, match_closest=True, throw_error=True)
            print(f"✅ Successfully opened: {name}")
            opened.append(name)
            
        except Exception as e:
            print(f"⚠️ Jarvis: App '{name}' not found on system. Trying web fallback...")
            try:
                url = f"https://www.{name_lower.replace(' ', '')}.com"
                webbrowser.open(url)
                opened.append(f"{name} (web)")
            except Exception as web_e:
                print(f"❌ Failed to open {name} completely: {web_e}")
                failed.append(name)

    if not silent and (opened or failed):
        try:
        
            success_names = [n for n in opened if " (web)" not in n]
            if success_names:
                msg = f"Sir, {', '.join(success_names)} khol diya."
                print(f"🎙️ {msg}")
   
            if failed:
                fail_msg = f"Sir, {', '.join(failed)} nahi khul paaya."
                print(f"🎙️ {fail_msg}")
        except:
            pass
            
    return opened

if __name__ == "__main__":
    apps_test = ["calculator", "youtube", "facebook"] 
    opened_apps = open_any_app(apps_test)
    print(f"\nFinal Opened List: {opened_apps}")