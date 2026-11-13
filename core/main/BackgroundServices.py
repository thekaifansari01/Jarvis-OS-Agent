import os
import sys
import subprocess
import platform
import logging
import threading
from dotenv import load_dotenv
from core.utils.ProcessManager import proc_manager
from core.voice.stt_status import exit_stt_popup
from core.main.TelegramRemoteBot import (
    start_telegram_remote_listener,
    stop_telegram_remote_listener,
    is_telegram_remote_running
)

load_dotenv()

_panel_process = None
_stt_popup_process = None
_baileys_process = None
_mobile_bridge_process = None
_mobile_bridge_start_time = 0.0
_rag_engine_initialized = False
_rag_dashboard_active = False
_rag_engine_init_started = False
_telegram_remote_init_started = False
_portal_process = None

def start_agent_panel():
    global _panel_process
    stop_agent_panel()
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        panel_module_file = os.path.join(base_dir, "core", "ui", "AgentPanel", "AgentPanel.py")
        if not os.path.exists(panel_module_file):
            logging.warning(f"AgentPanel.py not found at {panel_module_file} — skipping start.")
            return
        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
        _panel_process = proc_manager.spawn(
            [sys.executable, "-m", "core.ui.AgentPanel.AgentPanel"],
            cwd=base_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
        logging.info("Agent panel started successfully (module mode).")
    except Exception as e:
        logging.error(f"Agent panel start failed: {e}")

def stop_agent_panel():
    global _panel_process
    if _panel_process:
        try:
            proc_manager.kill_process_tree(_panel_process.pid)
            _panel_process.wait(timeout=2)
            logging.info("Agent panel stopped successfully.")
        except Exception as e:
            logging.error(f"Error stopping Agent panel: {e}")
        _panel_process = None

def is_agent_panel_running() -> bool:
    global _panel_process
    if _panel_process is None:
        return False
    return _panel_process.poll() is None

def start_stt_popup():
    global _stt_popup_process

    try:
        from core.voice import stt
        if not getattr(stt.engine, 'mic_available', False):
            logging.info("Mic not available — skipping STT popup.")
            return
    except Exception as e:
        logging.warning(f"Could not verify mic status, skipping STT popup: {e}")
        return

    stop_stt_popup()
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        popup_script = os.path.join(base_dir, "core", "ui", "SttPopup", "SttPopup.py")

        if os.path.exists(popup_script):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0

            _stt_popup_process = proc_manager.spawn(
                [sys.executable, popup_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            logging.info("STT popup started successfully.")
        else:
            logging.warning("SttPopup.py not found. Skipping STT popup.")
    except Exception as e:
        logging.error(f"STT popup start failed: {e}")

def stop_stt_popup():
    global _stt_popup_process
    try:
        exit_stt_popup()
    except Exception:
        pass
    if _stt_popup_process:
        try:
            proc_manager.kill_process_tree(_stt_popup_process.pid)
            _stt_popup_process.wait(timeout=2)
            logging.info("STT popup stopped successfully.")
        except Exception as e:
            logging.error(f"Error stopping STT popup: {e}")
        _stt_popup_process = None

def is_stt_popup_running() -> bool:
    global _stt_popup_process
    if _stt_popup_process is None:
        return False
    return _stt_popup_process.poll() is None

def start_baileys_server():
    global _baileys_process
    stop_baileys_server()
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        baileys_dir = os.path.join(base_dir, "tools", "Messanger", "whatsapp", "BaileysServer")
        script_path = os.path.join(baileys_dir, "baileys_service.js")
        session_creds_path = os.path.join(base_dir, "Data", "SessionCookies", "auth_info_baileys", "creds.json")
        if os.path.exists(script_path):
            if not os.path.exists(session_creds_path):
                logging.info("WhatsApp not logged in. Skipping server start.")
                return
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _baileys_process = proc_manager.spawn(
                ["node", script_path],
                cwd=baileys_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            logging.info("Baileys server started successfully.")
    except Exception as e:
        logging.error(f"Baileys server start failed: {e}")

def stop_baileys_server():
    global _baileys_process
    if _baileys_process:
        try:
            proc_manager.kill_process_tree(_baileys_process.pid)
            _baileys_process.wait(timeout=2)
            logging.info("Baileys server stopped successfully.")
        except Exception as e:
            logging.error(f"Error stopping Baileys server: {e}")
        _baileys_process = None

def is_baileys_running() -> bool:
    global _baileys_process
    if _baileys_process is None:
        return False
    return _baileys_process.poll() is None

def start_mobile_bridge():
    global _mobile_bridge_process, _mobile_bridge_start_time
    import time
    stop_mobile_bridge()
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bridge_script = os.path.join(base_dir, "tools", "MobileBridge", "server.py")
        if os.path.exists(bridge_script):
            creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            _mobile_bridge_process = proc_manager.spawn(
                [sys.executable, bridge_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            _mobile_bridge_start_time = time.time()
            logging.info("Mobile Bridge server started successfully.")
        else:
            logging.warning(f"Mobile Bridge script not found at {bridge_script}")
    except Exception as e:
        logging.error(f"Mobile Bridge server start failed: {e}")

def stop_mobile_bridge():
    global _mobile_bridge_process, _mobile_bridge_start_time
    if _mobile_bridge_process:
        try:
            proc_manager.kill_process_tree(_mobile_bridge_process.pid)
            _mobile_bridge_process.wait(timeout=2)
            logging.info("Mobile Bridge server stopped successfully.")
        except Exception as e:
            logging.error(f"Error stopping Mobile Bridge server: {e}")
        _mobile_bridge_process = None
        _mobile_bridge_start_time = 0.0
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        state_file = os.path.join(base_dir, "Data", "SessionCookies", "connected_devices.json")
        if os.path.exists(state_file):
            with open(state_file, "w", encoding="utf-8") as f:
                f.write("[]")
    except Exception:
        pass

def is_mobile_bridge_running() -> bool:
    global _mobile_bridge_process, _mobile_bridge_start_time
    import time
    if _mobile_bridge_process is None or _mobile_bridge_process.poll() is not None:
        return False
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 8090), timeout=1.5):
            return True
    except Exception:
        if time.time() - _mobile_bridge_start_time < 15.0:
            return _mobile_bridge_process.poll() is None
        return False

def start_unified_portal():
    global _portal_process
    import time

    if is_unified_portal_running():
        return

    stop_unified_portal()

    rag_port = None
    deadline = time.time() + 20.0
    while time.time() < deadline:
        try:
            from core.brain.Indexer.dashboard import get_dashboard_port
            p = get_dashboard_port()
            if p:
                rag_port = p
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not rag_port:
        logging.warning("Unified portal: RAG dashboard port unavailable — skipping start.")
        return

    mobile_port = 8090

    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        portal_module_file = os.path.join(base_dir, "core", "ui", "UnifiedPortal", "portal.py")
        if not os.path.exists(portal_module_file):
            logging.warning(f"Unified portal: portal.py not found at {portal_module_file}")
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0

        _portal_process = proc_manager.spawn(
            [
                sys.executable, "-m", "core.ui.UnifiedPortal.portal",
                "--rag-port", str(rag_port),
                "--mobile-port", str(mobile_port),
                "--portal-port", "8000",
            ],
            cwd=base_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        logging.info(f"Unified portal started at http://127.0.0.1:8000 (RAG: {rag_port}, Mobile: {mobile_port})")
    except Exception as e:
        logging.error(f"Unified portal start failed: {e}")

def stop_unified_portal():
    global _portal_process
    if _portal_process:
        try:
            proc_manager.kill_process_tree(_portal_process.pid)
            _portal_process.wait(timeout=2)
            logging.info("Unified portal stopped successfully.")
        except Exception as e:
            logging.error(f"Error stopping Unified portal: {e}")
        _portal_process = None

def is_unified_portal_running() -> bool:
    global _portal_process
    if _portal_process is None:
        return False
    if _portal_process.poll() is not None:
        return False
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 8000), timeout=1.5):
            return True
    except Exception:
        return _portal_process.poll() is None

def start_rag_engine():
    global _rag_engine_init_started, _rag_engine_initialized
    try:
        from core.brain.RagEngine import rag_engine
        _rag_engine_initialized = True
        _rag_engine_init_started = True
        logging.info("RAG Engine initialized successfully.")
        start_indexer_dashboard()
        start_unified_portal()
    except Exception as e:
        _rag_engine_init_started = False
        _rag_engine_initialized = False
        logging.error(f"RAG Engine initialization failed: {e}")

def stop_rag_engine():
    global _rag_engine_initialized, _rag_engine_init_started
    stop_indexer_dashboard()
    if _rag_engine_initialized:
        try:
            from core.brain.RagEngine import rag_engine
            rag_engine.shutdown()
        except Exception as e:
            logging.error(f"RAG Engine stop error: {e}")
        finally:
            _rag_engine_initialized = False
            _rag_engine_init_started = False
            logging.info("RAG Engine stopped successfully.")

def start_indexer_dashboard():
    global _rag_dashboard_active
    try:
        from core.brain.Indexer.dashboard import start_dashboard, is_dashboard_running
        if is_dashboard_running():
            _rag_dashboard_active = True
            logging.info("Indexer Dashboard already running.")
            return
        port = start_dashboard()
        if port:
            _rag_dashboard_active = True
            logging.info(f"Indexer Dashboard started at http://127.0.0.1:{port}")
        else:
            logging.warning("Indexer Dashboard failed to start.")
    except ImportError as e:
        logging.warning(f"Indexer Dashboard not available (missing dependency): {e}")
    except Exception as e:
        logging.error(f"Indexer Dashboard start failed: {e}")

def stop_indexer_dashboard():
    global _rag_dashboard_active
    if not _rag_dashboard_active:
        return
    try:
        from core.brain.Indexer.dashboard import stop_dashboard
        stop_dashboard()
        logging.info("Indexer Dashboard stopped successfully.")
    except Exception as e:
        logging.error(f"Indexer Dashboard stop failed: {e}")
    finally:
        _rag_dashboard_active = False

def is_indexer_dashboard_running() -> bool:
    try:
        from core.brain.Indexer.dashboard import is_dashboard_running
        return is_dashboard_running()
    except Exception:
        return False

def is_rag_engine_init_started() -> bool:
    return _rag_engine_init_started

def is_telegram_remote_init_started() -> bool:
    return _telegram_remote_init_started

def is_stt_mic_available() -> bool:
    try:
        from core.voice import stt
        return bool(getattr(stt.engine, "mic_available", False))
    except Exception:
        return False

def start_telegram_remote_service():
    global _telegram_remote_init_started
    _telegram_remote_init_started = True
    try:
        session_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "SessionCookies")
        token_file = os.path.join(session_dir, "telegram_bot_token.enc")
        if not os.path.exists(token_file):
            return
        if is_telegram_remote_running():
            return
        if start_telegram_remote_listener():
            logging.info("Telegram Remote Bot Service started successfully.")
    except Exception as e:
        logging.error(f"Telegram Remote Bot Service start failed: {e}")

def stop_telegram_remote_service():
    global _telegram_remote_init_started
    _telegram_remote_init_started = False
    try:
        stop_telegram_remote_listener()
    except Exception as e:
        logging.error(f"Error stopping Telegram Remote Bot Service: {e}")

def is_telegram_remote_service_running() -> bool:
    return is_telegram_remote_running()

def start_mcp_service():
    try:
        from core.mcp.MCPManager import mcp_manager
        mcp_manager.start()
    except Exception as e:
        logging.error(f"MCP service start failed: {e}")

def stop_mcp_service():
    try:
        from core.mcp.MCPManager import mcp_manager
        mcp_manager.stop()
    except Exception as e:
        logging.error(f"MCP service stop failed: {e}")

def is_mcp_enabled() -> bool:
    try:
        from core.mcp.MCPManager import mcp_manager
        return mcp_manager.is_enabled()
    except Exception:
        return False

def is_mcp_running() -> bool:
    try:
        from core.mcp.MCPManager import mcp_manager
        return mcp_manager.is_alive()
    except Exception:
        return True

def is_mcp_ready() -> bool:
    try:
        from core.mcp.MCPManager import mcp_manager
        return mcp_manager.is_ready()
    except Exception:
        return True

def stop_all_services():
    logging.info("Initiating shutdown of all background services.")
    stop_tasks = [
        stop_unified_portal,
        stop_agent_panel,
        stop_stt_popup,
        stop_baileys_server,
        stop_mobile_bridge,
        stop_telegram_remote_service,
        stop_rag_engine,
        stop_mcp_service
    ]
    threads = []
    for task in stop_tasks:
        t = threading.Thread(target=task, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=2.5)