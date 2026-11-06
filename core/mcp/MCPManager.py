from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
import os
import re
import threading
import time

from core.logger.logger import logger


class MCPManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._sync_lock = threading.Lock()
        self._bridge = None
        self._clients = {}
        self._tool_declarations = []
        self._servers_config = {}
        self._enabled = False
        self._started = False
        self._init_thread = None
        self._watcher_thread = None
        self._stop_event = threading.Event()
        self._init_done_event = threading.Event()
        self._last_mtime = None

    @staticmethod
    def get_config_path():
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(base_dir, "Data", "mcp_servers.json")

    @classmethod
    def _get_config_mtime(cls):
        path = cls.get_config_path()
        try:
            if os.path.exists(path):
                return os.path.getmtime(path)
        except Exception:
            pass
        return None

    @classmethod
    def load_raw_config(cls):
        path = cls.get_config_path()
        if not os.path.exists(path):
            return {"mcpServers": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"mcpServers": {}}
            if not isinstance(data.get("mcpServers"), dict):
                data["mcpServers"] = {}
            return data
        except Exception as e:
            raise RuntimeError(f"Failed to read {path}: {e}")

    @classmethod
    def save_raw_config(cls, data):
        path = cls.get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = f"{path}.{os.getpid()}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)

    @staticmethod
    def _extract_active_servers(config_dict):
        raw_servers = config_dict.get("mcpServers") if isinstance(config_dict, dict) else None
        if not isinstance(raw_servers, dict):
            return {}
        active = {}
        for name, cfg in raw_servers.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("disabled") is True or cfg.get("enabled") is False:
                continue
            active[name] = copy.deepcopy(cfg)
        return active

    @staticmethod
    def _is_mcp_package_available():
        try:
            import mcp
            _ = mcp
            return True
        except ImportError:
            return False

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            self._init_done_event.clear()

        if not self._is_mcp_package_available():
            logger.warning("MCP: 'mcp' package not installed. Run 'pip install mcp'.")
            with self._lock:
                self._started = False
                self._enabled = False
                self._init_done_event.set()
            return

        self._last_mtime = self._get_config_mtime()
        has_active = self._load_config_and_validate()

        if has_active:
            self._init_thread = threading.Thread(
                target=self._init_servers,
                daemon=True,
                name="MCPInit",
            )
            self._init_thread.start()
        else:
            self._init_done_event.set()

        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="MCPWatcher",
        )
        self._watcher_thread.start()

    def _load_config_and_validate(self):
        config_path = self.get_config_path()

        if not os.path.exists(config_path):
            logger.info("MCP: config not found, standing by for hot-reload.")
            with self._lock:
                self._servers_config = {}
                self._enabled = False
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"MCP: config read failed: {e}")
            with self._lock:
                self._servers_config = {}
                self._enabled = False
            return False

        active_servers = self._extract_active_servers(config)
        if not active_servers:
            logger.info("MCP: no active servers configured, standing by for hot-reload.")
            with self._lock:
                self._servers_config = {}
                self._enabled = False
            return False

        with self._lock:
            self._servers_config = active_servers
            self._enabled = True
        return True

    def _ensure_bridge(self):
        with self._lock:
            if self._bridge is not None and self._bridge.is_started():
                return self._bridge

        from core.mcp.AsyncBridge import AsyncBridge

        bridge = AsyncBridge()
        bridge.start()
        with self._lock:
            self._bridge = bridge
        return bridge

    def _connect_single_server(self, name, cfg, bridge):
        from core.mcp.MCPClient import MCPClient
        from core.mcp.ToolBridge import clear_server_tool_routes, convert_mcp_tools

        client = MCPClient(name, cfg, bridge)
        client.connect()
        clear_server_tool_routes(name)
        decls = convert_mcp_tools(name, client.tools)
        safe_prefix = f"mcp__{re.sub(r'[^a-zA-Z0-9_-]', '_', str(name).strip())}__"

        with self._lock:
            old_client = self._clients.get(name)
            self._clients[name] = client
            self._tool_declarations = [
                d
                for d in self._tool_declarations
                if not getattr(d, "name", "").startswith(safe_prefix)
            ]
            self._tool_declarations.extend(decls)
            self._enabled = True

        if old_client is not None and old_client is not client:
            try:
                old_client.close()
            except Exception:
                pass

        logger.info(f"MCP: server '{name}' connected ({len(decls)} tools).")
        return name, len(decls)

    def _disconnect_single_server(self, name):
        from core.mcp.ToolBridge import clear_server_tool_routes

        with self._lock:
            client = self._clients.pop(name, None)

        removed_routes = clear_server_tool_routes(name)
        safe_prefix = f"mcp__{re.sub(r'[^a-zA-Z0-9_-]', '_', str(name).strip())}__"

        with self._lock:
            self._tool_declarations = [
                d
                for d in self._tool_declarations
                if getattr(d, "name", "") not in removed_routes
                and not getattr(d, "name", "").startswith(safe_prefix)
            ]
            if not self._clients:
                self._enabled = False

        if client is not None:
            try:
                client.close()
            except Exception:
                pass
            logger.info(f"MCP: server '{name}' disconnected and unloaded.")

    def _init_servers(self, servers_config=None):
        with self._sync_lock:
            try:
                if servers_config is None:
                    with self._lock:
                        servers_config = copy.deepcopy(self._servers_config)
                if not servers_config:
                    with self._lock:
                        self._enabled = False
                    return

                try:
                    from core.mcp.ToolBridge import clear_tool_routes
                    clear_tool_routes()
                except Exception as e:
                    logger.error(f"MCP: ToolBridge import failed: {e}")
                    with self._lock:
                        self._enabled = False
                    return

                try:
                    bridge = self._ensure_bridge()
                except Exception as e:
                    logger.error(f"MCP: bridge start failed: {e}")
                    with self._lock:
                        self._enabled = False
                    return

                max_workers = min(max(len(servers_config), 1), 6)
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="MCPConnect") as pool:
                    future_map = {
                        pool.submit(self._connect_single_server, name, cfg, bridge): name
                        for name, cfg in servers_config.items()
                    }
                    for fut in as_completed(future_map):
                        srv_name = future_map[fut]
                        try:
                            fut.result()
                        except Exception as e:
                            logger.error(f"MCP: server '{srv_name}' connect failed: {e}")

                with self._lock:
                    client_count = len(self._clients)
                    total_decls = len(self._tool_declarations)

                if client_count > 0:
                    logger.info(
                        f"MCP: ready with {total_decls} tools from {client_count} servers."
                    )
                else:
                    logger.warning("MCP: no servers connected successfully.")
                    with self._lock:
                        self._enabled = False
            finally:
                self._init_done_event.set()

    def _watch_loop(self):
        self._init_done_event.wait()
        while not self._stop_event.wait(timeout=2.0):
            if not self._started:
                break
            current_mtime = self._get_config_mtime()
            if current_mtime != self._last_mtime:
                time.sleep(0.15)
                self._last_mtime = self._get_config_mtime()
                try:
                    self._sync_servers_from_disk()
                except Exception as e:
                    logger.error(f"MCP hot-reload error: {e}")

    def _sync_servers_from_disk(self):
        with self._sync_lock:
            if not self._started:
                return

            config_path = self.get_config_path()
            if not os.path.exists(config_path):
                new_active = {}
            else:
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        raw_cfg = json.load(f)
                    new_active = self._extract_active_servers(raw_cfg)
                except Exception as e:
                    logger.error(f"MCP hot-reload: failed to parse config: {e}")
                    return

            with self._lock:
                old_active = copy.deepcopy(self._servers_config)
                current_clients = set(self._clients.keys())

            all_known = set(old_active.keys()) | current_clients
            to_remove = [name for name in all_known if name not in new_active]
            to_add = [name for name in new_active if name not in all_known]
            to_restart = [
                name
                for name in new_active
                if name in all_known and old_active.get(name) != new_active.get(name)
            ]

            if not to_remove and not to_add and not to_restart:
                return

            logger.info(
                f"MCP (Hot-Reload): change detected | add={to_add} | remove={to_remove} | update={to_restart}"
            )

            for name in to_remove + to_restart:
                self._disconnect_single_server(name)

            with self._lock:
                self._servers_config = copy.deepcopy(new_active)

            connect_targets = to_add + to_restart
            if connect_targets:
                try:
                    bridge = self._ensure_bridge()
                except Exception as e:
                    logger.error(f"MCP (Hot-Reload): bridge start failed: {e}")
                    return

                max_workers = min(max(len(connect_targets), 1), 6)
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="MCPHotReload") as pool:
                    future_map = {
                        pool.submit(
                            self._connect_single_server,
                            name,
                            new_active[name],
                            bridge,
                        ): name
                        for name in connect_targets
                    }
                    for fut in as_completed(future_map):
                        srv_name = future_map[fut]
                        try:
                            fut.result()
                        except Exception as e:
                            logger.error(f"MCP (Hot-Reload): server '{srv_name}' failed: {e}")

            with self._lock:
                client_count = len(self._clients)
                total_decls = len(self._tool_declarations)
                self._enabled = client_count > 0

            logger.info(
                f"MCP (Hot-Reload): sync complete ({total_decls} tools active across {client_count} servers)."
            )

    def is_enabled(self):
        with self._lock:
            return self._enabled

    def is_alive(self):
        with self._lock:
            if not self._enabled:
                return True
            if self._init_thread is not None and self._init_thread.is_alive():
                return True
            if self._clients:
                return True
        return False

    def is_ready(self):
        with self._lock:
            if not self._enabled:
                return True
            thread = self._init_thread
        if thread is not None and thread.is_alive():
            return False
        return True

    def get_tool_declarations(self):
        with self._lock:
            enabled = self._enabled
            has_decls = bool(self._tool_declarations)
        if enabled and not has_decls and not self._init_done_event.is_set():
            self._init_done_event.wait(timeout=4.0)
        with self._lock:
            return list(self._tool_declarations)

    def get_prompt_summary(self):
        decls = self.get_tool_declarations()
        if not decls:
            return ""
        lines = [
            "<connected_mcp_tools>",
            "The following external MCP server tools are LIVE and ready. When a user request matches any of these tools or servers, prioritize calling the exact MCP tool directly:",
        ]
        for d in decls[:60]:
            t_name = getattr(d, "name", "")
            t_desc = (getattr(d, "description", "") or "").replace("\n", " ").strip()[:160]
            if t_name:
                lines.append(f"  - {t_name}: {t_desc}")
        lines.append("</connected_mcp_tools>")
        return "\n".join(lines)

    def get_router_hint(self):
        with self._lock:
            server_names = list(self._clients.keys())
            decls = list(self._tool_declarations)
        if not server_names and not decls:
            return ""
        tool_names = [getattr(d, "name", "") for d in decls[:40] if getattr(d, "name", "")]
        return (
            f"Connected external MCP servers: {', '.join(server_names)}. "
            f"Available MCP tools: {', '.join(tool_names)}. "
            "If the user command asks to use MCP or any of these external servers/tools, ALWAYS route to 'AGENTIC'."
        )

    def matches_command(self, command_text):
        if not command_text:
            return False
        cmd_lower = str(command_text).lower()
        if re.search(r"\bmcp\b", cmd_lower):
            return True
        with self._lock:
            server_names = list(self._clients.keys())
            clients = list(self._clients.values())
        for s_name in server_names:
            clean_s = s_name.lower().strip()
            if len(clean_s) >= 3 and clean_s in cmd_lower:
                return True
        for client in clients:
            for tool in getattr(client, "tools", []) or []:
                raw_t = str(getattr(tool, "name", "")).lower().strip()
                if len(raw_t) >= 4 and raw_t in cmd_lower:
                    return True
        return False

    def call_tool_from_full_name(self, full_name, arguments):
        if not isinstance(full_name, str):
            return "Observation: [ERROR] [MCP] Invalid tool name"
        try:
            from core.mcp.ToolBridge import resolve_mcp_tool_name
            server_name, tool_name = resolve_mcp_tool_name(full_name)
        except Exception:
            server_name, tool_name = None, None

        if not server_name or not tool_name:
            return f"Observation: [ERROR] [MCP] Invalid tool name: {full_name}"
        return self.call_tool(server_name, tool_name, arguments)

    def call_tool(self, server_name, tool_name, arguments):
        with self._lock:
            client = self._clients.get(server_name)
            cfg = self._servers_config.get(server_name)

        if client is None and cfg is not None:
            try:
                bridge = self._ensure_bridge()
                self._connect_single_server(server_name, cfg, bridge)
                with self._lock:
                    client = self._clients.get(server_name)
            except Exception as e:
                return f"Observation: [ERROR] [MCP:{server_name}] Server reconnect failed: {e}"

        if client is None:
            return f"Observation: [ERROR] [MCP:{server_name}] Server not connected"

        try:
            raw = client.call_tool(tool_name, arguments or {})
        except Exception as e:
            err_type = type(e).__name__.lower()
            if "timeout" in err_type:
                return (
                    f"Observation: [ERROR] [MCP:{server_name}] "
                    f"Tool '{tool_name}' timed out"
                )
            return (
                f"Observation: [ERROR] [MCP:{server_name}] "
                f"Tool '{tool_name}' failed: {e}"
            )
        try:
            from core.mcp.ToolBridge import format_tool_result
            return format_tool_result(raw, server_name)
        except Exception as e:
            return f"Observation: [ERROR] [MCP:{server_name}] Result format error: {e}"

    def stop(self):
        self._stop_event.set()
        with self._lock:
            if not self._started and not self._enabled and not self._clients:
                return
            self._started = False
            self._enabled = False
            clients = list(self._clients.values())
            self._clients = {}
            self._tool_declarations = []
            bridge = self._bridge
            self._bridge = None
            self._init_thread = None
            self._watcher_thread = None
            self._init_done_event.set()

        for client in clients:
            try:
                client.close()
            except Exception:
                pass

        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass

        try:
            from core.mcp.ToolBridge import clear_tool_routes
            clear_tool_routes()
        except Exception:
            pass

        logger.info("MCP: stopped.")


mcp_manager = MCPManager()