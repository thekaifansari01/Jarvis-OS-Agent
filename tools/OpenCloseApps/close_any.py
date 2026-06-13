import traceback
from AppOpener import close

def close_any_app(apps_to_close):
    """
    Jarvis-level App Closer using AppOpener.
    Safely closes apps (UWP & Win32) without force killing or hardcoded lists.
    """
    closed = []
    
    if isinstance(apps_to_close, str):
        apps_to_close = [apps_to_close]

    for name in apps_to_close:
        name_lower = name.lower().strip()
        print(f"🔄 Jarvis: Attempting to smoothly close '{name}'...")
        
        try:
            close(name_lower, match_closest=True, throw_error=True)
            
            print(f"✅ Successfully closed: {name}")
            closed.append(name)
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "not running" in error_msg:
                print(f"⚠️ Jarvis: '{name}' is not currently running.")
            elif "not found" in error_msg:
                print(f"❌ Jarvis: Could not find any app matching '{name}' on this system.")
            else:
                print(f"❌ Jarvis: Unexpected error while closing '{name}'.")
                print(f"   Details: {e}")

    return closed

if __name__ == "__main__":
    apps = ["calculator", "notepad", "whatsapp"]
    closed_apps = close_any_app(apps)
    print(f"\nFinal Closed List: {closed_apps}")