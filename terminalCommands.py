import asyncio
import getpass
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv

from core.logger.logger import logger
from core.security import load_decrypted_token, save_encrypted_token

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(PROJECT_ROOT, ".jarvis.lock")
SESSION_DIR = os.path.join(PROJECT_ROOT, "Data", "SessionCookies")

CRED_PATHS = {
    "whatsapp": os.path.join(SESSION_DIR, "auth_info_baileys", "creds.json"),
    "telegram": os.path.join(SESSION_DIR, "jarvis_telegram_session.session"),
    "mail": os.path.join(SESSION_DIR, "token.enc"),
    "calendar": os.path.join(SESSION_DIR, "calendar_token.enc"),
}

SERVICE_LABELS = {
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "mail": "Gmail",
    "calendar": "Google Calendar",
}


def _is_pid_active_jarvis(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False

    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        name = (proc.name() or "").lower()
        cmdline = " ".join(proc.cmdline() or []).lower()
        return any(k in name or k in cmdline for k in ("python", "jarvis"))
    except ImportError:
        pass
    except Exception:
        return False

    if platform.system() == "Windows":
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                creationflags=creationflags,
                 stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            ).lower()
            if str(pid) in output and ("python" in output or "jarvis" in output):
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def is_jarvis_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            raise ValueError("Empty lock file")
        pid = int(content.splitlines()[0].strip())
        if _is_pid_active_jarvis(pid):
            return True
    except ValueError:
        logger.warning("Lock file corrupted. Proceeding with auto-cleanup.")
    except Exception:
        pass

    remove_lock_file()
    return False


def create_lock_file() -> None:
    try:
        temp_lock = f"{LOCK_FILE}.{os.getpid()}.tmp"
        with open(temp_lock, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_lock, LOCK_FILE)
    except Exception as e:
        logger.warning(f"Could not create lock file: {e}")


def remove_lock_file() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        logger.warning(f"Could not remove lock file: {e}")


def _handle_remove_readonly(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except Exception:
        pass


def safe_delete(path: str, retries: int = 3, delay: float = 0.5) -> bool:
    if not os.path.lexists(path):
        return False
    for attempt in range(1, retries + 1):
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, onerror=_handle_remove_readonly)
                return not os.path.lexists(path)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
                os.remove(path)
                return not os.path.lexists(path)
        except PermissionError:
            if attempt < retries:
                time.sleep(delay)
            else:
                return False
        except FileNotFoundError:
            return True
        except Exception:
            if attempt < retries:
                time.sleep(delay)
            else:
                return False
    return False


def get_user_confirmation(prompt_text: str) -> bool:
    while True:
        try:
            ans = input(f"{prompt_text} (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Invalid input. Please enter 'y' or 'n'.")


def _prompt_secret(prompt_text: str) -> str:
    try:
        if sys.stdin and sys.stdin.isatty():
            value = getpass.getpass(prompt_text).strip()
            if value:
                return value
    except Exception:
        pass
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def deleteMemory() -> None:
    try:
        target_folder = os.path.join(PROJECT_ROOT, "Data", "jarvis_memory")
        if not os.path.exists(target_folder):
            logger.info("Memory is already cleared. Nothing to delete.")
            return

        if safe_delete(target_folder):
            logger.info("Memory cleared successfully.")
        else:
            logger.warning("Could not clear memory completely. Please check file permissions.")
    except Exception as e:
        logger.error(f"Error encountered while clearing memory: {e}")


def _revoke_google_token(token_file_path: str) -> None:
    if not os.path.exists(token_file_path):
        return
    try:
        token_data = load_decrypted_token(token_file_path)
        if not isinstance(token_data, dict):
            return
        revoke_target = token_data.get("refresh_token") or token_data.get("token") or token_data.get("access_token")
        if revoke_target:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": revoke_target},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
    except Exception:
        pass


async def _revoke_telegram_session() -> None:
    session_base = os.path.join(SESSION_DIR, "jarvis_telegram_session")
    session_file = f"{session_base}.session"
    if not os.path.exists(session_file):
        return
    try:
        from telethon import TelegramClient
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
        api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        if not api_id.isdigit() or not api_hash:
            return
        logging.getLogger("telethon").setLevel(logging.CRITICAL)
        client = TelegramClient(session_base, int(api_id), api_hash)
        await asyncio.wait_for(client.connect(), timeout=5)
        try:
            if await asyncio.wait_for(client.is_user_authorized(), timeout=5):
                await asyncio.wait_for(client.log_out(), timeout=5)
        finally:
            await client.disconnect()
    except Exception:
        pass


def deleteSessionCookies(*targets: str) -> None:
    if not targets:
        logger.warning("No service specified.")
        return

    paths_map = {
        "whatsapp": [
            os.path.join(SESSION_DIR, "auth_info_baileys"),
            os.path.join(SESSION_DIR, "chats.db"),
            os.path.join(SESSION_DIR, "chats.db-wal"),
            os.path.join(SESSION_DIR, "chats.db-shm"),
        ],
        "calendar": [
            os.path.join(SESSION_DIR, "calendar_token.enc"),
        ],
        "mail": [
            os.path.join(SESSION_DIR, "token.enc"),
        ],
        "telegram": [
            os.path.join(SESSION_DIR, "jarvis_telegram_session.session"),
            os.path.join(SESSION_DIR, "jarvis_telegram_session.session-journal"),
            os.path.join(SESSION_DIR, "jarvis_telegram_session.session-wal"),
            os.path.join(SESSION_DIR, "jarvis_telegram_session.session-shm"),
        ],
    }

    services_logged_out = []
    already_logged_out = []
    failed_services = []

    for target in targets:
        key = str(target).strip().lower()
        if key not in paths_map:
            failed_services.append(str(target))
            continue

        path_list = paths_map[key]
        exists = any(os.path.lexists(p) for p in path_list)
        service_name = SERVICE_LABELS.get(key, key.capitalize())

        if not exists:
            already_logged_out.append(service_name)
            continue

        if key in ("mail", "calendar"):
            _revoke_google_token(path_list[0])
        elif key == "telegram":
            try:
                asyncio.run(_revoke_telegram_session())
            except Exception:
                pass

        all_deleted = True
        for item_path in path_list:
            if os.path.lexists(item_path):
                if not safe_delete(item_path):
                    all_deleted = False

        if all_deleted:
            services_logged_out.append(service_name)
        else:
            failed_services.append(service_name)

    if already_logged_out:
        logger.info(f"Already logged out: {', '.join(already_logged_out)}")
    if services_logged_out:
        logger.info(f"Successfully logged out: {', '.join(services_logged_out)}")
    if failed_services:
        logger.warning(f"Failed to logout completely (files in use or invalid service): {', '.join(failed_services)}")


async def _run_telegram_login() -> bool:
    from telethon import TelegramClient
    from telethon.errors import PhoneCodeInvalidError, PhoneNumberInvalidError, SessionPasswordNeededError
    from telethon.utils import get_display_name

    logging.getLogger("telethon").setLevel(logging.CRITICAL)

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = os.path.join(SESSION_DIR, "jarvis_telegram_session")

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    print("\n" + "=" * 65)
    print(" 📱 \033[1;36mJARVIS TELEGRAM SECURE AUTHENTICATION\033[0m")
    print("=" * 65)

    if not api_id_raw or not api_hash or not api_id_raw.isdigit():
        print(" ❌ \033[1;31mERROR: Valid TELEGRAM_API_ID or TELEGRAM_API_HASH missing in .env\033[0m")
        print("=" * 65 + "\n")
        return False

    client = TelegramClient(session_file, int(api_id_raw), api_hash)
    await client.connect()

    try:
        if not await client.is_user_authorized():
            print(" 💡 \033[1;33mTIP: You MUST include your country code (e.g., +919876543210)\033[0m")
            print("-" * 65)
            phone = input(" 📞 Enter Phone Number : ").strip()

            if not phone:
                print("\n ❌ \033[1;31mERROR: Phone number cannot be empty.\033[0m")
                print("=" * 65 + "\n")
                return False

            if not phone.startswith("+"):
                print(" ⚠️ \033[1;33mWarning: Country code missing! Prepending '+' is required.\033[0m")

            try:
                await client.send_code_request(phone)
                print(" 📩 \033[1;32mOTP sent successfully! Please check your Telegram app.\033[0m")
                code = input(" 🔑 Enter OTP Code     : ").strip()

                try:
                    await client.sign_in(phone=phone, code=code)
                except SessionPasswordNeededError:
                    print("\n 🔐 \033[1;33mTwo-Step Verification (2FA) is enabled.\033[0m")
                    password = _prompt_secret(" 🔑 Enter 2FA Password : ")
                    await client.sign_in(password=password)
            except PhoneNumberInvalidError:
                print("\n ❌ \033[1;31mERROR: Invalid Phone Number! Did you forget the country code?\033[0m")
                print("=" * 65 + "\n")
                return False
            except PhoneCodeInvalidError:
                print("\n ❌ \033[1;31mERROR: Invalid OTP Code entered.\033[0m")
                print("=" * 65 + "\n")
                return False
            except Exception as e:
                print(f"\n ❌ \033[1;31mAUTHENTICATION FAILED: {e}\033[0m")
                print("=" * 65 + "\n")
                return False

        me = await client.get_me()
        name = get_display_name(me)
        print(f"\n ✅ \033[1;32mSUCCESS: Logged in successfully as {name}!\033[0m")
        print(" 📁 Session securely saved to: Data/SessionCookies/")
        print("=" * 65 + "\n")

        try:
            await client.send_message("me", "🤖 **Jarvis Telegram Session Authenticated Successfully!**")
        except Exception:
            pass

        return True
    finally:
        await client.disconnect()


def login_service(service: str) -> None:
    svc_name = SERVICE_LABELS.get(service, service.capitalize())

    if service in CRED_PATHS and os.path.exists(CRED_PATHS[service]):
        if not get_user_confirmation(f"{svc_name} is already logged in. Do you want to overwrite the existing session?"):
            logger.info(f"Skipping {svc_name} login.")
            return
        deleteSessionCookies(service)

    if service == "whatsapp":
        baileys_dir = os.path.join(PROJECT_ROOT, "tools", "Messanger", "whatsapp", "BaileysServer")
        script_path = os.path.join(baileys_dir, "baileys_service.js")
        if not os.path.exists(script_path):
            logger.error("WhatsApp login service script not found.")
            return
        if not shutil.which("node"):
            logger.error("Node.js is not installed or not in the system PATH. Please install Node.js to use WhatsApp.")
            return

        logger.info("Starting WhatsApp login. Scan the QR code from the popup window.")
        logger.info("Press Ctrl+C after scanning once connection is confirmed.")
        try:
            subprocess.run(["node", script_path], cwd=baileys_dir, check=True)
            if os.path.exists(CRED_PATHS["whatsapp"]):
                logger.info("WhatsApp login process finished successfully.")
            else:
                logger.warning("WhatsApp login exited before credentials were saved.")
        except subprocess.CalledProcessError as e:
            logger.error(f"WhatsApp login process failed with exit code {e.returncode}.")
        except KeyboardInterrupt:
            if os.path.exists(CRED_PATHS["whatsapp"]):
                logger.info("WhatsApp credentials saved. Login completed successfully.")
            else:
                logger.info("WhatsApp login process cancelled by the user.")
        except Exception as e:
            logger.error(f"WhatsApp login encountered an unexpected error: {e}")

    elif service == "telegram":
        try:
            logger.info("Initializing Telegram Interactive Setup...")
            success = asyncio.run(_run_telegram_login())
            if success:
                logger.info("Telegram login process finished successfully.")
            else:
                logger.error("Telegram login could not be completed.")
        except ImportError as e:
            logger.error(f"Required module missing for Telegram login: {e}")
        except KeyboardInterrupt:
            logger.info("Telegram login process cancelled by the user.")
        except Exception as e:
            logger.error(f"Telegram login encountered an unexpected error: {e}")

    elif service == "mail":
        try:
            from tools.Messanger.email_manager import authenticate_gmail
            logger.info("Starting Gmail login. The browser will open for authentication.")
            result = authenticate_gmail(interactive=True)
            service_obj = result[0] if isinstance(result, tuple) else result
            if service_obj:
                logger.info("Gmail login successful.")
            else:
                logger.error("Gmail login failed or timed out.")
        except ImportError as e:
            logger.error(f"Required module missing for Gmail login: {e}")
        except KeyboardInterrupt:
            logger.info("Gmail login cancelled by the user.")
        except Exception as e:
            logger.error(f"Gmail login encountered an unexpected error: {e}")

    elif service == "calendar":
        try:
            from tools.Calendar.CalendarTool import authenticate_calendar
            logger.info("Starting Google Calendar login. The browser will open for authentication.")
            result = authenticate_calendar(interactive=True)
            service_obj = result[0] if isinstance(result, tuple) else result
            if service_obj:
                logger.info("Calendar login successful.")
            else:
                logger.error("Calendar login failed.")
        except ImportError as e:
            logger.error(f"Required module missing for Google Calendar login: {e}")
        except KeyboardInterrupt:
            logger.info("Calendar login cancelled by the user.")
        except Exception as e:
            logger.error(f"Calendar login encountered an unexpected error: {e}")
    else:
        logger.error(f"Unknown service specified: {service}")


def show_help_menu() -> None:
    help_text = """
====================================================================
                        JARVIS HELP MENU
====================================================================

USAGE:
    jarvis                     Start Jarvis AI Voice Assistant
    jarvis --help              Show this help menu

UPDATE & SYSTEM MAINTENANCE:
    jarvis update                                        Check and apply updates
    jarvis update --check                                Check for updates without installing
    jarvis update --channel <stable|edge|pinned>         Switch release channel
    jarvis update --rollback                             Restore previous working version
    jarvis update --force                                Force re-sync codebase and packages
    jarvis uninstall                                     Run complete system uninstaller

MCP SERVER COMMANDS (Works Live with Zero-Restart Hot-Reload):
    jarvis mcp list                                      List all MCP servers
    jarvis mcp add <name> <cmd/url> [args...] [-e K=V]   Add or update an MCP server
    jarvis mcp remove <name>                             Remove an MCP server
    jarvis mcp enable <name>                             Enable a disabled MCP server
    jarvis mcp disable <name>                            Temporarily disable an MCP server
    jarvis mcp test <name>                               Test connection and list tools

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

TELEGRAM REMOTE BOT:
    jarvis bot --activate      Setup and activate the Remote Telegram Bot
    jarvis bot --deactivate    Revoke the token and stop the remote bot
    jarvis bot --status        Check if the remote bot is active

MEMORY & RESET COMMANDS (Jarvis must be OFF):
    jarvis memory --clear      Clear Jarvis memory and chat history
    jarvis reset --hard        Factory reset (clear memory and log out all services)

====================================================================
"""
    logger.info(help_text)


def _handle_bot_command(non_dev_args: list[str]) -> None:
    token_path = os.path.join(SESSION_DIR, "telegram_bot_token.enc")
    action_flags = [a for a in non_dev_args if a != "bot"]

    if any(k in action_flags for k in ("--status", "status")):
        if os.path.exists(token_path):
            try:
                data = load_decrypted_token(token_path)
                if isinstance(data, dict) and data.get("token"):
                    logger.info("Bot Status : ACTIVE")
                    logger.info(f"Bot Name   : {data.get('bot_name', 'Unknown')}")
                    logger.info(f"Username   : @{data.get('bot_username', 'Unknown')}")
                    logger.info(f"Chat ID    : {data.get('allowed_chat_id', 'Not Set')}")
                else:
                    raise ValueError("Decryption failed")
            except Exception:
                logger.warning("Bot Status : Active (However, the token file is corrupted or the encryption key is missing)")
        else:
            logger.info("Bot Status : INACTIVE (Not Configured)")
        return

    if any(k in action_flags for k in ("--activate", "activate")):
        if is_jarvis_running():
            logger.error("Jarvis is currently running! Please stop Jarvis first before activating or replacing the bot.")
            sys.exit(1)

        if os.path.exists(token_path):
            try:
                data = load_decrypted_token(token_path)
                if isinstance(data, dict) and data.get("bot_username"):
                    bot_username = data.get("bot_username", "Unknown")
                    if not get_user_confirmation(f"A Remote Bot (@{bot_username}) is already active. Do you want to replace it?"):
                        logger.info("Bot activation skipped.")
                        return
            except Exception:
                pass

        logger.info("Telegram Remote Bot Activation")
        token = _prompt_secret("Enter the Telegram Bot Token (from @BotFather): ")
        if not token or ":" not in token:
            logger.error("Invalid format! A valid Telegram Bot Token is required.")
            return

        try:
            logger.info("Verifying the Bot Token with the Telegram API...")
            res = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
            if res.status_code != 200:
                logger.error("Invalid Token! Telegram API authentication failed.")
                return

            payload = res.json()
            bot_data = payload.get("result", {}) if isinstance(payload, dict) else {}
            if not bot_data:
                logger.error("Invalid response format received from the Telegram server.")
                return

            bot_username = bot_data.get("username", "Unknown")
            bot_name = bot_data.get("first_name", "Jarvis Bot")

            logger.info("To find your Chat ID, message @userinfobot on Telegram.")
            while True:
                try:
                    chat_id_input = input("Enter your Telegram Chat ID (mandatory): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    logger.info("Bot activation cancelled.")
                    return

                if not chat_id_input:
                    logger.error("Chat ID is required for security. Please enter your Chat ID.")
                    continue
                if not chat_id_input.lstrip("-").isdigit():
                    logger.error("Invalid Chat ID. It must be a numeric ID (e.g., 123456789).")
                    continue
                break

            os.makedirs(SESSION_DIR, exist_ok=True)
            save_encrypted_token(
                {
                    "token": token,
                    "bot_name": bot_name,
                    "bot_username": bot_username,
                    "allowed_chat_id": chat_id_input,
                    "active": True,
                },
                token_path,
            )

            logger.info(f"SUCCESS: Bot @{bot_username} ({bot_name}) is now activated!")
            logger.info("The Remote Bot Service will automatically start when Jarvis is launched.")
        except ValueError:
            logger.error("Invalid JSON response received from the Telegram server.")
        except requests.exceptions.RequestException as e:
            logger.error(f"A connection error occurred while verifying the token: {e}")
        return

    if any(k in action_flags for k in ("--deactivate", "--revoke", "--delete", "deactivate", "revoke", "delete")):
        if is_jarvis_running():
            logger.error("Jarvis is currently running! Please stop Jarvis first before deactivating the bot.")
            sys.exit(1)

        if os.path.exists(token_path):
            try:
                data = load_decrypted_token(token_path)
                if isinstance(data, dict) and data.get("token"):
                    requests.post(
                        f"https://api.telegram.org/bot{data['token']}/deleteWebhook",
                        json={"drop_pending_updates": True},
                        timeout=5,
                    )
            except Exception:
                pass

        if safe_delete(token_path):
            logger.info("Telegram Remote Bot deactivated and the token was removed successfully.")
        else:
            logger.warning("No active Telegram Bot configuration was found.")
        return

    logger.warning("Usage: jarvis bot --activate | jarvis bot --deactivate | jarvis bot --status")


def _extract_target_services(args_list: list[str]) -> tuple[list[str], list[str]]:
    flag_map = {
        "--whatsapp": "whatsapp",
        "--telegram": "telegram",
        "--mail": "mail",
        "--calendar": "calendar",
    }
    valid_services = []
    unknown_flags = []

    for item in args_list:
        if item in ("login", "logout"):
            continue
        if item == "--all":
            return ["whatsapp", "telegram", "mail", "calendar"], []
        if item in flag_map:
            svc = flag_map[item]
            if svc not in valid_services:
                valid_services.append(svc)
        else:
            unknown_flags.append(item)

    return valid_services, unknown_flags


def _handle_mcp_command(raw_args: list[str]) -> None:
    from core.mcp.MCPManager import MCPManager

    mcp_idx = -1
    for i, token in enumerate(raw_args):
        if token.lower() == "mcp":
            mcp_idx = i
            break

    tokens = raw_args[mcp_idx + 1 :] if mcp_idx >= 0 else []
    action = tokens[0].lower().lstrip("-") if tokens else "list"
    rest = tokens[1:] if len(tokens) > 1 else []

    if action in ("list", "ls", "status"):
        try:
            data = MCPManager.load_raw_config()
        except Exception as e:
            logger.error(f"MCP config error: {e}")
            return

        servers = data.get("mcpServers", {})
        if not servers:
            logger.info("No MCP servers configured in Data/mcp_servers.json.")
            logger.info("Add one using: jarvis mcp add <name> <command_or_url> [args...]")
            return

        print("\n" + "=" * 78)
        print(f" {'SERVER NAME':<20} │ {'STATUS':<10} │ {'TYPE':<7} │ {'TARGET / COMMAND'}")
        print("=" * 78)
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            is_disabled = cfg.get("disabled") is True or cfg.get("enabled") is False
            status_str = "DISABLED" if is_disabled else "ENABLED"
            if cfg.get("url"):
                srv_type = "URL"
                target = str(cfg.get("url"))
            else:
                srv_type = "STDIO"
                cmd = str(cfg.get("command", ""))
                args_list = [str(x) for x in (cfg.get("args") or [])]
                target = f"{cmd} {' '.join(args_list)}".strip()
            env_count = len(cfg.get("env") or {}) if isinstance(cfg.get("env"), dict) else 0
            if env_count > 0:
                target = f"{target} [+{env_count} env]"
            print(f" {name:<20} │ {status_str:<10} │ {srv_type:<7} │ {target}")
        print("=" * 78 + "\n")
        return

    if action == "add":
        if len(rest) < 2:
            logger.warning(
                "Usage: jarvis mcp add <name> <command_or_url> [args...] [-e KEY=VALUE]"
            )
            logger.info(
                "Example: jarvis mcp add everything npx @modelcontextprotocol/server-everything"
            )
            return

        server_name = rest[0].strip()
        raw_tail = rest[1:]

        env_vars = {}
        headers = {}
        cwd_val = None
        timeout_val = None
        cmd_tokens = []
        after_double_dash = False

        idx = 0
        while idx < len(raw_tail):
            tok = raw_tail[idx]
            if tok == "--" and not after_double_dash:
                after_double_dash = True
                idx += 1
                continue

            if not after_double_dash:
                if tok in ("-e", "--env") and idx + 1 < len(raw_tail):
                    pair = raw_tail[idx + 1]
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k.strip():
                            env_vars[k.strip()] = v.strip()
                    idx += 2
                    continue
                if tok.startswith("--env="):
                    pair = tok[len("--env=") :]
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k.strip():
                            env_vars[k.strip()] = v.strip()
                    idx += 1
                    continue
                if tok in ("-H", "--header") and idx + 1 < len(raw_tail):
                    pair = raw_tail[idx + 1]
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k.strip():
                            headers[k.strip()] = v.strip()
                    elif ":" in pair:
                        k, v = pair.split(":", 1)
                        if k.strip():
                            headers[k.strip()] = v.strip()
                    idx += 2
                    continue
                if tok == "--cwd" and idx + 1 < len(raw_tail):
                    cwd_val = raw_tail[idx + 1].strip()
                    idx += 2
                    continue
                if tok == "--timeout" and idx + 1 < len(raw_tail):
                    try:
                        timeout_val = int(raw_tail[idx + 1])
                    except ValueError:
                        pass
                    idx += 2
                    continue

            cmd_tokens.append(tok)
            idx += 1

        if not cmd_tokens:
            logger.error("Missing command or URL for MCP server.")
            return

        first_target = cmd_tokens[0].strip()
        entry = {}

        if first_target.startswith("http://") or first_target.startswith("https://"):
            entry["url"] = first_target
            if headers:
                entry["headers"] = headers
        else:
            entry["command"] = first_target
            entry["args"] = cmd_tokens[1:]
            if env_vars:
                entry["env"] = env_vars
            if cwd_val:
                entry["cwd"] = cwd_val

        if timeout_val is not None:
            entry["timeout"] = timeout_val

        try:
            data = MCPManager.load_raw_config()
            existed = server_name in data["mcpServers"]
            data["mcpServers"][server_name] = entry
            MCPManager.save_raw_config(data)
            verb = "Updated" if existed else "Added"
            logger.info(f"MCP: {verb} server '{server_name}' in Data/mcp_servers.json.")
            if is_jarvis_running():
                logger.info("Jarvis is running — hot-reloading server automatically in the background.")
        except Exception as e:
            logger.error(f"Failed to save MCP server '{server_name}': {e}")
        return

    if action in ("remove", "rm", "delete", "del", "uninstall"):
        if not rest:
            logger.warning("Usage: jarvis mcp remove <name>")
            return
        server_name = rest[0].strip()
        try:
            data = MCPManager.load_raw_config()
            if server_name not in data["mcpServers"]:
                logger.warning(f"MCP server '{server_name}' not found.")
                return
            del data["mcpServers"][server_name]
            MCPManager.save_raw_config(data)
            logger.info(f"MCP: Removed server '{server_name}'.")
            if is_jarvis_running():
                logger.info("Jarvis is running — unloading server automatically in the background.")
        except Exception as e:
            logger.error(f"Failed to remove MCP server '{server_name}': {e}")
        return

    if action in ("enable", "disable"):
        if not rest:
            logger.warning(f"Usage: jarvis mcp {action} <name>")
            return
        server_name = rest[0].strip()
        disable_flag = action == "disable"
        try:
            data = MCPManager.load_raw_config()
            if server_name not in data["mcpServers"]:
                logger.warning(f"MCP server '{server_name}' not found.")
                return
            srv_cfg = data["mcpServers"][server_name]
            if not isinstance(srv_cfg, dict):
                srv_cfg = {}
            srv_cfg.pop("enabled", None)
            if disable_flag:
                srv_cfg["disabled"] = True
            else:
                srv_cfg.pop("disabled", None)
            data["mcpServers"][server_name] = srv_cfg
            MCPManager.save_raw_config(data)
            state_label = "disabled" if disable_flag else "enabled"
            logger.info(f"MCP: Server '{server_name}' is now {state_label}.")
            if is_jarvis_running():
                logger.info("Jarvis is running — syncing server state automatically in the background.")
        except Exception as e:
            logger.error(f"Failed to update MCP server '{server_name}': {e}")
        return

    if action == "test":
        if not rest:
            logger.warning("Usage: jarvis mcp test <name>")
            return
        server_name = rest[0].strip()
        try:
            data = MCPManager.load_raw_config()
        except Exception as e:
            logger.error(f"MCP config error: {e}")
            return

        srv_cfg = data.get("mcpServers", {}).get(server_name)
        if not isinstance(srv_cfg, dict):
            logger.error(f"MCP server '{server_name}' not found in Data/mcp_servers.json.")
            return

        logger.info(f"Testing connection to MCP server '{server_name}'...")
        from core.mcp.AsyncBridge import AsyncBridge
        from core.mcp.MCPClient import MCPClient

        bridge = AsyncBridge()
        client = None
        start_ts = time.perf_counter()
        try:
            bridge.start()
            client = MCPClient(server_name, srv_cfg, bridge)
            client.connect()
            elapsed = time.perf_counter() - start_ts
            tools = client.tools or []
            logger.info(
                f"SUCCESS: Server '{server_name}' connected in {elapsed:.2f}s ({len(tools)} tools discovered)."
            )
            for idx, t in enumerate(tools, 1):
                t_name = getattr(t, "name", "?")
                t_desc = (getattr(t, "description", "") or "").replace("\n", " ").strip()[:80]
                print(f"  {idx:>2}. {t_name:<32} - {t_desc}")
        except Exception as e:
            logger.error(f"FAILED: Could not connect to '{server_name}': {e}")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            try:
                bridge.stop()
            except Exception:
                pass
        return

    logger.warning(
        "Usage: jarvis mcp [list | add | remove | enable | disable | test]"
    )


def _find_powershell_exe() -> str | None:
    for candidate in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(candidate)
        if found:
            return found
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    fallback = os.path.join(sys_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.exists(fallback):
        return fallback
    return None


def _handle_update_command(raw_args: list[str]) -> None:
    if platform.system() != "Windows":
        logger.error("Automated PowerShell update manager is only supported on Windows.")
        sys.exit(1)

    ps_exe = _find_powershell_exe()
    if not ps_exe:
        logger.error("PowerShell executable not found on this system.")
        sys.exit(1)

    script_path = os.path.join(PROJECT_ROOT, "update.ps1")
    if not os.path.exists(script_path):
        logger.error(f"update.ps1 not found in {PROJECT_ROOT}.")
        sys.exit(1)

    upd_idx = -1
    for i, token in enumerate(raw_args):
        if token.lower() == "update":
            upd_idx = i
            break

    tokens = raw_args[upd_idx + 1 :] if upd_idx >= 0 else []
    ps_args = ["-InstallPath", PROJECT_ROOT]
    valid_channels = {"stable", "edge", "pinned"}

    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        low = tok.lower()

        if low in ("--check", "-check", "check", "--status", "status"):
            ps_args.append("-Check")
            idx += 1
            continue
        if low in ("--silent", "-silent", "--quiet", "-q"):
            ps_args.append("-Silent")
            idx += 1
            continue
        if low in ("--auto-update", "--autoupdate", "-autoupdate", "--auto", "--yes", "-y"):
            ps_args.append("-AutoUpdate")
            idx += 1
            continue
        if low in ("--rollback", "-rollback", "rollback", "--revert", "revert"):
            ps_args.append("-Rollback")
            idx += 1
            continue
        if low in ("--force", "-force", "-f"):
            ps_args.append("-Force")
            idx += 1
            continue
        if low in ("--stable", "--edge", "--pinned"):
            ps_args.extend(["-Channel", low.lstrip("-")])
            idx += 1
            continue
        if low in ("--channel", "-channel") and idx + 1 < len(tokens):
            ch_val = tokens[idx + 1].strip().lower()
            if ch_val not in valid_channels:
                logger.error(f"Invalid channel '{ch_val}'. Choose from: stable, edge, pinned.")
                sys.exit(1)
            ps_args.extend(["-Channel", ch_val])
            idx += 2
            continue
        if low.startswith("--channel="):
            ch_val = low.split("=", 1)[1].strip()
            if ch_val not in valid_channels:
                logger.error(f"Invalid channel '{ch_val}'. Choose from: stable, edge, pinned.")
                sys.exit(1)
            ps_args.extend(["-Channel", ch_val])
            idx += 1
            continue
        if low in ("--cooldown", "-edgepromptcooldowndays") and idx + 1 < len(tokens):
            days_str = tokens[idx + 1].strip()
            if not days_str.isdigit():
                logger.error("Cooldown days must be an integer.")
                sys.exit(1)
            ps_args.extend(["-EdgePromptCooldownDays", days_str])
            idx += 2
            continue
        if low.startswith("--cooldown="):
            days_str = low.split("=", 1)[1].strip()
            if not days_str.isdigit():
                logger.error("Cooldown days must be an integer.")
                sys.exit(1)
            ps_args.extend(["-EdgePromptCooldownDays", days_str])
            idx += 1
            continue

        logger.error(f"Unknown update option: {tok}")
        logger.info("Usage: jarvis update [--check] [--channel stable|edge|pinned] [--rollback] [--force] [--auto-update] [--silent]")
        sys.exit(1)

    cmd = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path, *ps_args]
    try:
        res = subprocess.run(cmd, cwd=os.path.expanduser("~"))
        sys.exit(res.returncode)
    except KeyboardInterrupt:
        print()
        logger.info("Update cancelled by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Failed to execute update manager: {e}")
        sys.exit(1)


def _handle_uninstall_command(raw_args: list[str]) -> None:
    if platform.system() != "Windows":
        logger.error("Automated PowerShell uninstaller is only supported on Windows.")
        sys.exit(1)

    ps_exe = _find_powershell_exe()
    if not ps_exe:
        logger.error("PowerShell executable not found on this system.")
        sys.exit(1)

    script_path = os.path.join(PROJECT_ROOT, "uninstall.ps1")
    if not os.path.exists(script_path):
        logger.error(f"uninstall.ps1 not found in {PROJECT_ROOT}.")
        sys.exit(1)

    import tempfile
    temp_script = os.path.join(tempfile.gettempdir(), f"jarvis_uninstall_{os.getpid()}.ps1")
    try:
        shutil.copy2(script_path, temp_script)
    except Exception:
        temp_script = script_path

    cmd = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", temp_script, "-InstallPath", PROJECT_ROOT]
    try:
        res = subprocess.run(cmd, cwd=os.path.expanduser("~"))
        os._exit(res.returncode)
    except KeyboardInterrupt:
        print()
        logger.info("Uninstallation cancelled by user.")
        os._exit(130)
    except Exception as e:
        logger.error(f"Failed to execute uninstaller: {e}")
        os._exit(1)


def handle_cli_commands() -> bool:
    raw_args = [arg.strip() for arg in sys.argv[1:] if arg.strip()]
    args = [arg.lower() for arg in raw_args]
    if not args:
        return False

    dev_flags = {"test_jarvis", "no_wake"}
    non_dev_raw = [
        a for a in raw_args if a.lower() not in dev_flags and not a.lower().startswith("voice=")
    ]
    non_dev_args = [a.lower() for a in non_dev_raw]

    if not non_dev_args:
        return False

    if non_dev_args[0] == "mcp":
        _handle_mcp_command(non_dev_raw)
        return True

    if any(h in non_dev_args for h in ("help", "--help", "-h")):
        show_help_menu()
        return True

    subcommands = {"login", "logout", "memory", "reset", "bot", "mcp", "update", "uninstall"}
    matched_subcommands = [cmd for cmd in non_dev_args if cmd in subcommands]

    if not matched_subcommands:
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
            "--hard": "jarvis reset --hard",
            "--update": "jarvis update",
            "upgrade": "jarvis update",
            "--upgrade": "jarvis update",
            "--rollback": "jarvis update --rollback",
            "rollback": "jarvis update --rollback",
            "--uninstall": "jarvis uninstall",
        }
        logger.error("Invalid command. Type 'jarvis --help' to view the available commands.")
        for arg in non_dev_args:
            if arg in alias_map:
                logger.info(f"Did you mean: '{alias_map[arg]}'?")
                break
        return True

    unique_subcommands = list(dict.fromkeys(matched_subcommands))
    if len(unique_subcommands) > 1:
        logger.error(f"Conflicting subcommands specified: {', '.join(unique_subcommands)}. Please run one command at a time.")
        return True

    primary_cmd = unique_subcommands[0]

    if primary_cmd == "bot":
        _handle_bot_command(non_dev_args)
        return True

    if primary_cmd == "mcp":
        _handle_mcp_command(non_dev_raw)
        return True

    if primary_cmd == "update":
        _handle_update_command(non_dev_raw)
        return True

    if primary_cmd == "uninstall":
        _handle_uninstall_command(non_dev_raw)
        return True

    if is_jarvis_running():
        logger.error("Jarvis is currently running! Please stop Jarvis first before executing CLI setup commands.")
        sys.exit(1)

    logger.info("Executing command...")

    if primary_cmd == "login":
        services, unknown = _extract_target_services(non_dev_args)
        if unknown:
            logger.error(f"Unknown option(s) for login: {', '.join(unknown)}")
            logger.info("Valid options: --whatsapp, --telegram, --mail, --calendar, --all")
            return True
        if not services:
            logger.warning("Please specify a service: --whatsapp, --telegram, --mail, --calendar, or --all")
            logger.info("Type 'jarvis --help' for usage details.")
        else:
            for svc in services:
                login_service(svc)

    elif primary_cmd == "logout":
        targets, unknown = _extract_target_services(non_dev_args)
        if unknown:
            logger.error(f"Unknown option(s) for logout: {', '.join(unknown)}")
            logger.info("Valid options: --whatsapp, --telegram, --mail, --calendar, --all")
            return True
        if not targets:
            logger.warning("Please specify a service: --whatsapp, --telegram, --mail, --calendar, or --all")
            logger.info("Type 'jarvis --help' for usage details.")
        else:
            deleteSessionCookies(*targets)

    elif primary_cmd == "memory":
        extra_args = [a for a in non_dev_args if a != "memory"]
        if extra_args and all(a in ("--clear", "--purge") for a in extra_args):
            if get_user_confirmation("Are you sure you want to clear Jarvis's memory? This will delete past context."):
                deleteMemory()
            else:
                logger.info("Memory clear operation aborted.")
        else:
            logger.warning("Use 'jarvis memory --clear' to clear the memory.")
            logger.info("Type 'jarvis --help' for usage details.")

    elif primary_cmd == "reset":
        extra_args = [a for a in non_dev_args if a != "reset"]
        if extra_args == ["--hard"]:
            if get_user_confirmation("WARNING: This will factory reset Jarvis (clear all memory and log out all services). Are you absolutely sure?"):
                logger.info("Factory reset is in progress...")
                deleteMemory()
                deleteSessionCookies("whatsapp", "telegram", "mail", "calendar")
                token_path = os.path.join(SESSION_DIR, "telegram_bot_token.enc")
                safe_delete(token_path)
                logger.info("Factory reset completed successfully.")
            else:
                logger.info("Factory reset operation aborted.")
        else:
            logger.warning("Use 'jarvis reset --hard' to perform a factory reset.")
            logger.info("Type 'jarvis --help' for usage details.")

    return True