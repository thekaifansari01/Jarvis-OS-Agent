from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import threading

from core.logger.logger import logger


class MCPManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._bridge = None
        self._clients = {}
        self._tool_declarations = []
        self._servers_config = {}
        self._enabled = False
        self._started = False
        self._init_thread = None
        self._init_done_event = threading.Event()

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            self._init_done_event.clear()

        if not self._load_config_and_validate():
            with self._lock:
                self._started = False
                self._enabled = False
                self._init_done_event.set()
            return

        self._init_thread = threading.Thread(
            target=self._init_servers,
            daemon=True,
            name="MCPInit",
        )
        self._init_thread.start()

    def _load_config_and_validate(self):
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        config_path = os.path.join(base_dir, "Data", "mcp_servers.json")

        if not os.path.exists(config_path):
            logger.info("MCP: config not found, MCP disabled.")
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"MCP: config read failed: {e}")
            return False

        raw_servers = config.get("mcpServers") if isinstance(config, dict) else None
        if not isinstance(raw_servers, dict) or not raw_servers:
            logger.info("MCP: no servers configured, MCP disabled.")
            return False

        active_servers = {}
        for name, cfg in raw_servers.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("disabled") is True or cfg.get("enabled") is False:
                continue
            active_servers[name] = cfg

        if not active_servers:
            logger.info("MCP: all configured servers are disabled.")
            return False

        try:
            import mcp
            _ = mcp
        except ImportError:
            logger.warning("MCP: 'mcp' package not installed. Run 'pip install mcp'.")
            return False

        with self._lock:
            self._servers_config = active_servers
            self._enabled = True
        return True

    def _connect_single_server(self, name, cfg, bridge):
        from core.mcp.MCPClient import MCPClient
        from core.mcp.ToolBridge import convert_mcp_tools

        client = MCPClient(name, cfg, bridge)
        client.connect()
        decls = convert_mcp_tools(name, client.tools)
        with self._lock:
            self._clients[name] = client
            self._tool_declarations.extend(decls)
        logger.info(f"MCP: server '{name}' connected ({len(decls)} tools).")
        return name, len(decls)

    def _init_servers(self, servers_config=None):
        try:
            if servers_config is None:
                with self._lock:
                    servers_config = dict(self._servers_config)
            if not servers_config:
                with self._lock:
                    self._enabled = False
                return

            try:
                from core.mcp.AsyncBridge import AsyncBridge
                from core.mcp.ToolBridge import clear_tool_routes
                clear_tool_routes()
            except Exception as e:
                logger.error(f"MCP: AsyncBridge import failed: {e}")
                with self._lock:
                    self._enabled = False
                return

            try:
                bridge = AsyncBridge()
                bridge.start()
                with self._lock:
                    self._bridge = bridge
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
            bridge = self._bridge

        if client is None and cfg is not None and bridge is not None:
            try:
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