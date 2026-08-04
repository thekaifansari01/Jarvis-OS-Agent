import os
import sys
import shutil
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(PROJECT_ROOT, ".jarvis.lock")

def is_jarvis_running():
    return os.path.exists(LOCK_FILE)

def create_lock_file():
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"⚠️ [WARNING] Could not create lock file: {e}")

def remove_lock_file():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"⚠️ [WARNING] Could not remove lock file: {e}")

def safe_delete(path, retries=3, delay=0.5):
    if not os.path.exists(path):
        print(f"⚠️ [WARNING] Target does not exist: {path}")
        return False

    for attempt in range(1, retries + 1):
        try:
            if os.path.isdir(path):
                def remove_readonly(func, path, exc_info):
                    import stat
                    os.chmod(path, stat.S_IWRITE)
                    func(path)

                shutil.rmtree(path, onerror=remove_readonly)
                print(f"✅ [SUCCESS] Folder deleted: {os.path.basename(path)}")
                return True

            elif os.path.isfile(path) or os.path.islink(path):
                os.chmod(path, 0o777)
                os.remove(path)
                print(f"✅ [SUCCESS] File deleted: {os.path.basename(path)}")
                return True

        except PermissionError:
            print(f"🔒 [PERMISSION ERROR] File or folder is locked or access is denied: {path} (Attempt {attempt}/{retries})")
            if attempt < retries:
                time.sleep(delay)
            else:
                print(f"❌ [FAILED] File might be locked by another process. Please delete manually: {path}")

        except FileNotFoundError:
            print(f"⚠️ [WARNING] File not found during deletion: {path}")
            return True

        except OSError as e:
            print(f"⚠️ [OS ERROR] System error occurred ({e.strerror}): {path}")
            break

        except Exception as e:
            print(f"❌ [UNEXPECTED ERROR] {type(e).__name__}: {e}")
            break

    return False

def deleteMemory():
    try:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        target_folder = os.path.join(root_dir, "Jarvis", "core", "brain", "memory")
        
        print("\n--- Deleting Memory ---")
        safe_delete(target_folder)
        
    except Exception as e:
        print(f"❌ [CRITICAL] Error resolving memory path: {e}")

def deleteSessionCookies(*targets):
    if not targets:
        print("⚠️ [WARNING] No target specified.")
        return

    try:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        session_dir = os.path.join(root_dir, "Data", "SessionCookies")

        paths_map = {
            "whatsapp": [
                os.path.join(session_dir, "auth_info_baileys"),
                os.path.join(session_dir, "chats.db")
            ],
            "calendar": [
                os.path.join(session_dir, "calendar_token.json")
            ],
            "mail": [
                os.path.join(session_dir, "token.json")
            ]
        }

        print("\n--- Deleting Session Cookies ---")
        for target in targets:
            key = str(target).strip().lower()

            if key not in paths_map:
                print(f"❌ [INVALID TARGET] '{target}' is not a valid option. Use: 'whatsapp', 'calendar', 'mail'")
                continue

            path_list = paths_map[key]
            for item_path in path_list:
                safe_delete(item_path)

    except Exception as e:
        print(f"❌ [CRITICAL] Issue occurred during session deletion process: {e}")

def show_help_menu():
    print("""
====================================================================
                        🤖 JARVIS CLI HELP MENU                     
====================================================================

USAGE:
    jarvis [COMMAND] [OPTIONS]

COMMANDS:
    (No Command)          Start the Jarvis AI Voice Assistant normal mode.
    help, --help, -h      Display this help menu.

LOGOUT & SESSION COMMANDS (Requires Jarvis to be OFF):
    jarvis logout --whatsapp         Logout WhatsApp & clear chats.db
    jarvis logout --mail             Logout Email session
    jarvis logout --calendar         Logout Google Calendar session
    jarvis logout --mail --calendar  Logout multiple services at once
    jarvis logout --all              Logout from all connected services

MEMORY & RESET COMMANDS (Requires Jarvis to be OFF):
    jarvis memory --clear            Clear AI contextual memory & history
    jarvis reset --hard              FACTORY RESET: Wipe memory & all sessions

====================================================================
""")

def handle_cli_commands():
    args = [arg.lower() for arg in sys.argv[1:]]
    subcommands = {"logout", "memory", "reset", "help", "--help", "-h"}

    if not any(arg in subcommands for arg in args):
        return False

    if any(h in args for h in ("help", "--help", "-h")):
        show_help_menu()
        return True

    if is_jarvis_running():
        print("\n❌ [ERROR] Jarvis is currently running!")
        print("⚠️  Please stop Jarvis before running cleanup commands.\n")
        sys.exit(1)

    print("\n⚡ [JARVIS CLI] Executing terminal command...")

    if "logout" in args:
        targets = []
        if "--whatsapp" in args:
            targets.append("whatsapp")
        if "--mail" in args:
            targets.append("mail")
        if "--calendar" in args:
            targets.append("calendar")
        if "--all" in args:
            targets = ["whatsapp", "mail", "calendar"]

        if not targets:
            print("⚠️ [WARNING] Please specify a service: --whatsapp, --mail, --calendar, or --all")
            print("💡 Tip: Type 'jarvis --help' to see all usage options.")
        else:
            deleteSessionCookies(*targets)

    if "memory" in args:
        if "--clear" in args or "--purge" in args:
            deleteMemory()
        else:
            print("⚠️ [WARNING] Use 'jarvis memory --clear' to delete brain memory.")
            print("💡 Tip: Type 'jarvis --help' to see all usage options.")

    if "reset" in args:
        if "--hard" in args:
            print("🚨 [HARD RESET] Deleting all sessions and memory...")
            deleteMemory()
            deleteSessionCookies("whatsapp", "mail", "calendar")
        else:
            print("⚠️ [WARNING] Use 'jarvis reset --hard' to completely wipe data.")
            print("💡 Tip: Type 'jarvis --help' to see all usage options.")

    return True