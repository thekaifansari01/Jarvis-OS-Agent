import os
import sys
import winreg

def register_custom_protocol():
    protocol_name = "jarvis"

    current_dir = os.path.dirname(os.path.abspath(__file__))
    handler_script = os.path.join(current_dir, "JarvisProtocol.py")

    python_exe = sys.executable

    command = f'"{python_exe}" "{handler_script}" "%1"'

    try:
        key_path = fr"Software\Classes\{protocol_name}"

        winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{protocol_name.capitalize()} Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        command_key_path = fr"{key_path}\shell\open\command"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, command_key_path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

        print("✅ SUCCESS: Windows Registry successfully updated.")
        print(f"🔗 The 'jarvis://' protocol is now linked to: {handler_script}")
        
    except Exception as e:
        print(f"❌ ERROR: Failed to update the Windows Registry. Details: {e}")

if __name__ == "__main__":
    print("⚙️ Initializing Custom URL Protocol setup for Jarvis...")
    register_custom_protocol()
    input("\nPress Enter to exit...")