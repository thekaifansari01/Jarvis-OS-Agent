import os
import sys
import shutil
import time
import subprocess
import platform
from pathlib import Path
from core.logger.logger import logger

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(PROJECT_ROOT, ".jarvis.lock")

def is_jarvis_running():
    return os.path.exists(LOCK_FILE)

def create_lock_file():
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Could not create lock file: {e}")

def remove_lock_file():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        logger.warning(f"Could not remove lock file: {e}")

def safe_delete(path, retries=3, delay=0.5):
    if not os.path.exists(path):
        return False
    for attempt in range(1, retries + 1):
        try:
            if os.path.isdir(path):
                def remove_readonly(func, path, exc_info):
                    import stat
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(path, onerror=remove_readonly)
                return True
            elif os.path.isfile(path) or os.path.islink(path):
                os.chmod(path, 0o777)
                os.remove(path)
                return True
        except PermissionError:
            if attempt < retries:
                time.sleep(delay)
            else:
                return False
        except FileNotFoundError:
            return True
        except Exception:
            return False
    return False

def deleteMemory():
    try:
        target_folder = os.path.join(PROJECT_ROOT, "Data", "jarvis_memory")
        if safe_delete(target_folder):
            logger.info("Memory cleared successfully.")
        else:
            logger.warning("Could not clear memory. Please close Jarvis and try again.")
    except Exception:
        logger.warning("Could not clear memory. Please close Jarvis and try again.")

def deleteSessionCookies(*targets):
    if not targets:
        logger.warning("No service specified.")
        return
    try:
        session_dir = os.path.join(PROJECT_ROOT, "Data", "SessionCookies")
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
            ],
            "telegram": [
                os.path.join(session_dir, "jarvis_telegram_session.session"),
                os.path.join(session_dir, "jarvis_telegram_session.session-journal")
            ]
        }
        services_logged_out = []
        failed_services = []
        for target in targets:
            key = str(target).strip().lower()
            if key not in paths_map:
                failed_services.append(target)
                continue
            path_list = paths_map[key]
            all_deleted = True
            for item_path in path_list:
                if not safe_delete(item_path):
                    all_deleted = False
                    break
            if all_deleted:
                service_name = {
                    "whatsapp": "WhatsApp",
                    "calendar": "Calendar",
                    "mail": "Gmail",
                    "telegram": "Telegram"
                }.get(key, key.capitalize())
                services_logged_out.append(service_name)
            else:
                failed_services.append(target)
        if services_logged_out:
            logger.info(f"{', '.join(services_logged_out)} logged out successfully.")
        if failed_services:
            logger.warning(f"Could not logout: {', '.join(failed_services)}")
        if not services_logged_out and not failed_services:
            logger.warning("No services specified.")
    except Exception:
        logger.warning("Could not logout services. Please close Jarvis and try again.")

def login_service(service: str):
    if service == "whatsapp":
        baileys_dir = os.path.join(PROJECT_ROOT, "tools", "Messanger", "whatsapp", "BaileysServer")
        script_path = os.path.join(baileys_dir, "baileys_service.js")
        if not os.path.exists(script_path):
            logger.error("WhatsApp login service not found.")
            return
        logger.info("Starting WhatsApp login. Scan QR code from the popup window.")
        logger.info("Press Ctrl+C after scanning to complete the process.")
        try:
            subprocess.run(["node", script_path], cwd=baileys_dir, check=False)
            logger.info("WhatsApp login completed.")
        except KeyboardInterrupt:
            logger.info("WhatsApp login process completed.")
        except Exception:
            logger.error("WhatsApp login failed.")
            
    elif service == "telegram":
        try:
            logger.info("Starting Telegram login. Please enter your Phone Number and OTP below.")
            subprocess.run([
                sys.executable, "-c",
                "import os, sys; sys.path.append(os.getcwd()); "
                "from tools.Messanger.telegram.telegram import send_telegram_message; "
                "send_telegram_message('me', 'Jarvis Telegram Session Authenticated Successfully!')"
            ], check=False)
            logger.info("Telegram login process completed.")
        except KeyboardInterrupt:
            logger.info("Telegram login process cancelled.")
        except Exception as e:
            logger.error(f"Telegram login failed: {e}")
            
    elif service == "mail":
        try:
            from tools.Messanger.email_manager import authenticate_gmail
            logger.info("Starting Gmail login. Browser will open for authentication.")
            service_obj = authenticate_gmail(interactive=True)
            if service_obj:
                logger.info("Gmail login successful.")
            else:
                logger.error("Gmail login failed or timed out.")
        except Exception:
            logger.error("Gmail login failed.")
            
    elif service == "calendar":
        try:
            from tools.Calendar.CalendarTool import authenticate_calendar
            logger.info("Starting Google Calendar login. Browser will open for authentication.")
            service_obj, status = authenticate_calendar(interactive=True)
            if service_obj:
                logger.info("Calendar login successful.")
            else:
                logger.error("Calendar login failed.")
        except Exception:
            logger.error("Calendar login failed.")
    else:
        logger.error(f"Unknown service: {service}")

def show_help_menu():
    help_text = """
====================================================================
                        🤖 JARVIS HELP MENU
====================================================================

USAGE:
    jarvis                     Start Jarvis AI Voice Assistant
    jarvis --help              Show this help menu

LOGIN COMMANDS (Jarvis must be OFF):
    jarvis login --whatsapp    Login to WhatsApp
    jarvis login --telegram    Login to Telegram
    jarvis login --mail        Login to Gmail
    jarvis login --calendar    Login to Google Calendar
    jarvis login --all         Login to all services

LOGOUT COMMANDS (Jarvis must be OFF):
    jarvis logout --whatsapp   Logout from WhatsApp
    jarvis logout --telegram   Logout from Telegram
    jarvis logout --mail       Logout from Gmail
    jarvis logout --calendar   Logout from Google Calendar
    jarvis logout --all        Logout from all services

MEMORY & RESET COMMANDS (Jarvis must be OFF):
    jarvis memory --clear      Clear Jarvis memory and chat history
    jarvis reset --hard        Factory reset (clear memory + all logins)

====================================================================
"""
    logger.info(help_text)

def handle_cli_commands():
    args = [arg.lower() for arg in sys.argv[1:]]
    if not args:
        return False
    dev_flags = {"test_jarvis", "no_wake"}
    non_dev_args = [a for a in args if a not in dev_flags and not a.startswith("voice=")]
    if not non_dev_args:
        return False
    if any(h in non_dev_args for h in ("help", "--help", "-h")):
        show_help_menu()
        return True
    subcommands = {"logout", "memory", "reset", "login"}
    has_valid_subcommand = any(arg in subcommands for arg in non_dev_args)
    if not has_valid_subcommand:
        alias_map = {
            "--clear": "jarvis memory --clear",
            "-c": "jarvis memory --clear",
            "clear": "jarvis memory --clear",
            "mem": "jarvis memory --clear",
            "lgout": "jarvis logout --all",
            "log": "jarvis logout --all",
            "signout": "jarvis logout --all",
            "purge": "jarvis reset --hard",
            "factory": "jarvis reset --hard",
            "--hard": "jarvis reset --hard"
        }
        logger.error("Invalid command. Type 'jarvis --help' to see available commands.")
        for arg in non_dev_args:
            if arg in alias_map:
                logger.info(f"Did you mean: '{alias_map[arg]}'?")
                break
        return True
    if is_jarvis_running():
        logger.error("Jarvis is currently running! Please stop Jarvis first.")
        sys.exit(1)
    logger.info("Executing command...")
    
    if "login" in non_dev_args:
        services = []
        if "--whatsapp" in non_dev_args: services.append("whatsapp")
        if "--telegram" in non_dev_args: services.append("telegram")
        if "--mail" in non_dev_args: services.append("mail")
        if "--calendar" in non_dev_args: services.append("calendar")
        if "--all" in non_dev_args:
            services = ["whatsapp", "telegram", "mail", "calendar"]
            
        if not services:
            logger.warning("Please specify a service: --whatsapp, --telegram, --mail, --calendar, or --all")
            logger.info("Type 'jarvis --help' for usage.")
        else:
            for svc in services:
                login_service(svc)
                
    if "logout" in non_dev_args:
        targets = []
        if "--whatsapp" in non_dev_args: targets.append("whatsapp")
        if "--telegram" in non_dev_args: targets.append("telegram")
        if "--mail" in non_dev_args: targets.append("mail")
        if "--calendar" in non_dev_args: targets.append("calendar")
        if "--all" in non_dev_args:
            targets = ["whatsapp", "telegram", "mail", "calendar"]
            
        if not targets:
            logger.warning("Please specify a service: --whatsapp, --telegram, --mail, --calendar, or --all")
            logger.info("Type 'jarvis --help' for usage.")
        else:
            deleteSessionCookies(*targets)
            
    if "memory" in non_dev_args:
        if "--clear" in non_dev_args or "--purge" in non_dev_args:
            deleteMemory()
        else:
            logger.warning("Use 'jarvis memory --clear' to clear memory.")
            logger.info("Type 'jarvis --help' for usage.")
            
    if "reset" in non_dev_args:
        if "--hard" in non_dev_args:
            logger.info("Factory reset in progress...")
            deleteMemory()
            deleteSessionCookies("whatsapp", "telegram", "mail", "calendar")
            logger.info("Factory reset completed.")
        else:
            logger.warning("Use 'jarvis reset --hard' to factory reset.")
            logger.info("Type 'jarvis --help' for usage.")
            
    return True