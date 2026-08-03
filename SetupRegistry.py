import os
import sys
import winreg
import ctypes
import subprocess
import traceback

def is_venv_activated():
    return (sys.prefix != sys.base_prefix) or ("VIRTUAL_ENV" in os.environ)

def is_registry_already_setup():
    try:
        key_path = r"Software\Classes\jarvis\shell\open\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return bool(value)
    except Exception:
        return False

def is_cli_already_installed(current_dir):
    exe_path = os.path.join(current_dir, ".venv", "Scripts", "jarvis.exe")
    return os.path.exists(exe_path)

def is_path_already_added(current_dir):
    venv_scripts_path = os.path.join(current_dir, ".venv", "Scripts")
    try:
        key_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            current_path, _ = winreg.QueryValueEx(key, "Path")
            paths = [os.path.normcase(os.path.normpath(p.strip())) for p in current_path.split(";") if p.strip()]
            target_norm = os.path.normcase(os.path.normpath(venv_scripts_path))
            return target_norm in paths
    except Exception:
        return False

def create_setup_file(current_dir):
    setup_path = os.path.join(current_dir, "setup.py")
    if os.path.exists(setup_path):
        return True
    
    setup_content = """from setuptools import setup, find_packages

setup(
    name="jarvis-cli",
    version="1.0.0",
    packages=find_packages(),
    py_modules=["main"],
    entry_points={
        "console_scripts": [
            "jarvis=main:main",
        ],
    },
)
"""
    try:
        with open(setup_path, "w", encoding="utf-8") as f:
            f.write(setup_content)
        print("✅ SUCCESS: Automatically generated 'setup.py'.")
        return True
    except Exception as e:
        print(f"❌ ERROR: Failed to create 'setup.py': {e}")
        return False

def register_custom_protocol(current_dir):
    protocol_name = "jarvis"
    handler_script = os.path.join(current_dir, "JarvisProtocol.py")
    
    if not os.path.exists(handler_script):
        print(f"⚠️ WARNING: 'JarvisProtocol.py' not found at {handler_script}.")

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

        print("✅ SUCCESS: URL Protocol 'jarvis://' registered.")
        return True
    except PermissionError:
        print("❌ ERROR: Permission denied while writing to Windows Registry. Run as Administrator.")
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to register URL protocol: {e}")
        return False

def install_cli_package(current_dir):
    setup_file = os.path.join(current_dir, "setup.py")
    if not os.path.exists(setup_file):
        print("❌ ERROR: 'setup.py' missing. Cannot build CLI command.")
        return False

    try:
        print("⚙️ Building 'jarvis' CLI command inside virtual environment...")
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", "-e", "."],
            cwd=current_dir,
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print("✅ SUCCESS: 'jarvis' CLI command installed.")
            return True
        else:
            print(f"❌ ERROR: pip install failed:\n{result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("❌ ERROR: Python executable or pip module not found.")
        return False
    except Exception as e:
        print(f"❌ ERROR: Unexpected error during CLI installation: {e}")
        return False

def add_venv_to_system_path(current_dir):
    venv_scripts_path = os.path.join(current_dir, ".venv", "Scripts")
    
    if not os.path.exists(venv_scripts_path):
        print(f"⚠️ WARNING: Virtual environment folder not found at: {venv_scripts_path}")
        return False

    try:
        key_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""

            new_path = f"{current_path};{venv_scripts_path}" if current_path else venv_scripts_path
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                SMTO_ABORTIFHUNG, 5000, ctypes.byref(ctypes.c_ulong())
            )
            print(f"✅ SUCCESS: Added to Windows PATH -> {venv_scripts_path}")
            return True
            
    except PermissionError:
        print("❌ ERROR: Permission denied while updating environment variables.")
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to update Windows PATH: {e}")
        return False

def main():
    print("🚀 Initializing Smart Jarvis Setup System...\n" + "=" * 50)
    
    try:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        in_venv = is_venv_activated()
        reg_setup = is_registry_already_setup()

        if not in_venv:
            print("⚠️ NOTICE: Virtual Environment (.venv) is NOT activated.")
            if reg_setup:
                print("ℹ️ INFO: URL Protocol ('jarvis://') is ALREADY configured in Windows Registry.")
                print("💡 ACTION REQUIRED: To configure the CMD 'jarvis' command, activate '.venv' and run this script again.")
            else:
                print("⚙️ Setting up URL Protocol ('jarvis://') only...")
                register_custom_protocol(root_dir)
                print("💡 ACTION REQUIRED: To configure the CMD 'jarvis' command, activate '.venv' and run this script again.")
            print("=" * 50)
            return

        cli_installed = is_cli_already_installed(root_dir)
        path_added = is_path_already_added(root_dir)

        if reg_setup and cli_installed and path_added:
            print("ℹ️ INFO: URL Protocol ('jarvis://') is already configured.")
            print("ℹ️ INFO: 'jarvis' CLI command is already installed.")
            print("ℹ️ INFO: '.venv\\Scripts' is already present in Windows PATH.")
            print("=" * 50)
            print("🎉 ALL COMPONENTS ARE ALREADY CONFIGURED! No changes needed.")
            return

        print("⚡ Active Virtual Environment detected. Verifying components...")

        if not reg_setup:
            register_custom_protocol(root_dir)
        else:
            print("ℹ️ INFO: URL Protocol ('jarvis://') is already configured.")

        if not cli_installed:
            if create_setup_file(root_dir):
                install_cli_package(root_dir)
        else:
            print("ℹ️ INFO: 'jarvis' CLI command is already installed.")

        if not path_added:
            add_venv_to_system_path(root_dir)
        else:
            print("ℹ️ INFO: '.venv\\Scripts' is already present in Windows PATH.")

        print("=" * 50)
        print("🎉 SETUP COMPLETED! Open a NEW Terminal window and type: jarvis")
        
    except Exception:
        print("❌ CRITICAL UNHANDLED ERROR:")
        traceback.print_exc()
    finally:
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()