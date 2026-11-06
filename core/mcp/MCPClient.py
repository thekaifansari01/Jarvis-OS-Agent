import asyncio
from contextlib import AsyncExitStack
import os
import shlex
import shutil
import sys
import tempfile

from core.logger.logger import logger


class MCPClient:
    def __init__(self, name, config, bridge):
        self.name = name
        self.config = config or {}
        self.bridge = bridge
        self.session = None
        self.tools = []
        self._connected = False
        self._task = None
        self._command_queue = None
        self._close_event = None
        self._ready_event = None
        self._start_error = None
        self._connect_lock = asyncio.Lock() if False else None

    def connect(self):
        if not isinstance(self.config, dict):
            raise RuntimeError(f"Invalid config for server '{self.name}'")
        has_command = bool(self.config.get("command"))
        has_url = bool(self.config.get("url"))
        if not has_command and not has_url:
            raise RuntimeError(f"Server '{self.name}' missing 'command' or 'url'")

        timeout = float(self.config.get("timeout", 60))
        self.bridge.run_coro(self._start_task(timeout=timeout), timeout=timeout + 5)

        if self._start_error is not None:
            raise self._start_error

        if not self._connected:
            raise RuntimeError(f"Server '{self.name}' failed to initialize")

    async def _start_task(self, timeout=60.0):
        if self._task is not None and not self._task.done():
            await self._stop_existing_task()

        loop = asyncio.get_running_loop()
        self._command_queue = asyncio.Queue()
        self._close_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._start_error = None
        self._connected = False

        self._task = loop.create_task(self._owner_loop(), name=f"MCPClient-{self.name}")
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._start_error = RuntimeError(
                f"Server '{self.name}' did not become ready within {int(timeout)}s"
            )
            self._close_event.set()
            if self._task is not None and not self._task.done():
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=3.0)
                except BaseException:
                    pass
            return

        if self._start_error is not None:
            raise self._start_error

    async def _stop_existing_task(self):
        if self._close_event is not None:
            self._close_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except BaseException:
                if not self._task.done():
                    self._task.cancel()
                    try:
                        await asyncio.wait_for(self._task, timeout=2.0)
                    except BaseException:
                        pass
            self._task = None

    def _build_environment(self):
        merged_env = dict(os.environ)
        merged_env["PYTHONUNBUFFERED"] = "1"
        merged_env.setdefault("NPM_CONFIG_YES", "true")
        merged_env.setdefault("CI", "true")

        env_override = self.config.get("env")
        if isinstance(env_override, dict):
            for k, v in env_override.items():
                if isinstance(k, str) and v is not None:
                    val_str = os.path.expandvars(str(v))
                    merged_env[k] = val_str
        return merged_env

    def _resolve_stdio_command(self, merged_env):
        raw_cmd = str(self.config.get("command", "")).strip()
        raw_args = self.config.get("args") or []
        if not isinstance(raw_args, list):
            raw_args = []
        args = [os.path.expandvars(str(a)) for a in raw_args]

        if not args and " " in raw_cmd and not os.path.exists(raw_cmd):
            parts = shlex.split(raw_cmd, posix=(sys.platform != "win32"))
            if parts:
                raw_cmd = parts[0]
                args = parts[1:]

        base_lower = os.path.basename(raw_cmd).lower()
        if base_lower in ("npx", "npx.cmd", "npx.exe"):
            if "-y" not in args and "--yes" not in args:
                args = ["-y"] + args

        path_env = merged_env.get("PATH") or os.environ.get("PATH")
        resolved = shutil.which(raw_cmd, path=path_env)

        if base_lower in ("python", "python3", "python.exe"):
            if not resolved or "windowsapps" in resolved.lower():
                resolved = sys.executable

        if sys.platform == "win32" and resolved:
            res_lower = resolved.lower()
            if res_lower.endswith("npx.cmd") or res_lower.endswith("npx.ps1"):
                node_dir = os.path.dirname(resolved)
                node_exe = os.path.join(node_dir, "node.exe")
                npx_cli = os.path.join(
                    node_dir, "node_modules", "npm", "bin", "npx-cli.js"
                )
                if os.path.isfile(node_exe) and os.path.isfile(npx_cli):
                    return node_exe, [npx_cli] + args

        return (resolved or raw_cmd), args

    @staticmethod
    def _read_stderr_tail(err_file, max_chars=600):
        if err_file is None:
            return ""
        try:
            err_file.flush()
            err_file.seek(0)
            content = err_file.read()
            if not content:
                return ""
            cleaned = content.strip()
            if len(cleaned) > max_chars:
                cleaned = "..." + cleaned[-max_chars:]
            return cleaned
        except Exception:
            return ""

    async def _owner_loop(self):
        err_file = None
        try:
            err_file = tempfile.TemporaryFile(
                mode="w+", encoding="utf-8", errors="replace"
            )
        except Exception:
            err_file = None

        try:
            await self._run_connection(err_file)
        except asyncio.CancelledError:
            if not self._ready_event.is_set() and self._start_error is None:
                self._start_error = RuntimeError(
                    f"Server '{self.name}' connection cancelled"
                )
        except BaseException as e:
            stderr_tail = self._read_stderr_tail(err_file)
            if stderr_tail:
                detailed_msg = f"{e} | stderr: {stderr_tail}"
                self._start_error = RuntimeError(detailed_msg)
                logger.error(f"MCP client '{self.name}' owner loop error: {detailed_msg}")
            else:
                self._start_error = e if isinstance(e, Exception) else RuntimeError(str(e))
                logger.error(f"MCP client '{self.name}' owner loop error: {e}")
        finally:
            self._connected = False
            self.session = None
            if not self._ready_event.is_set():
                self._ready_event.set()
            if err_file is not None:
                try:
                    err_file.close()
                except Exception:
                    pass

    async def _enter_transport(self, stack, err_file):
        url = self.config.get("url")
        if url:
            headers = self.config.get("headers") if isinstance(self.config.get("headers"), dict) else None
            transport_type = str(self.config.get("transport", "")).lower().strip()
            if transport_type == "sse" or str(url).rstrip("/").endswith("/sse"):
                from mcp.client.sse import sse_client
                streams = await stack.enter_async_context(
                    sse_client(str(url), headers=headers)
                )
                return streams[0], streams[1]
            try:
                from mcp.client.streamable_http import streamablehttp_client
                streams = await stack.enter_async_context(
                    streamablehttp_client(str(url), headers=headers)
                )
                return streams[0], streams[1]
            except ImportError:
                from mcp.client.sse import sse_client
                streams = await stack.enter_async_context(
                    sse_client(str(url), headers=headers)
                )
                return streams[0], streams[1]

        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        merged_env = self._build_environment()
        command, args = self._resolve_stdio_command(merged_env)
        cwd = self.config.get("cwd")

        params_kwargs = {
            "command": command,
            "args": args,
            "env": merged_env,
        }
        if cwd and os.path.isdir(str(cwd)):
            params_kwargs["cwd"] = str(cwd)

        try:
            params = StdioServerParameters(**params_kwargs)
        except TypeError:
            params_kwargs.pop("cwd", None)
            params = StdioServerParameters(**params_kwargs)

        if err_file is not None:
            try:
                return await stack.enter_async_context(
                    stdio_client(params, errlog=err_file)
                )
            except TypeError:
                return await stack.enter_async_context(stdio_client(params))
        return await stack.enter_async_context(stdio_client(params))

    async def _run_connection(self, err_file=None):
        from mcp import ClientSession

        async with AsyncExitStack() as stack:
            read_stream, write_stream = await self._enter_transport(stack, err_file)
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            self.session = session
            await session.initialize()
            tools_result = await session.list_tools()
            self.tools = list(getattr(tools_result, "tools", []) or [])
            self._connected = True
            self._ready_event.set()

            while not self._close_event.is_set():
                try:
                    command = await asyncio.wait_for(
                        self._command_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                if command is None:
                    break

                tool_name, arguments, future = command
                if future.cancelled():
                    continue
                try:
                    result = await session.call_tool(tool_name, arguments)
                    if not future.done():
                        future.set_result(result)
                except BaseException as e:
                    err_str = str(e).lower()
                    if any(
                        marker in err_str
                        for marker in (
                            "connection closed",
                            "endofstream",
                            "closedresourceerror",
                            "broken pipe",
                        )
                    ):
                        self._connected = False
                        if not future.done():
                            future.set_exception(
                                RuntimeError(f"MCP connection lost: {e}")
                            )
                        break
                    if not future.done():
                        future.set_exception(
                            e if isinstance(e, Exception) else RuntimeError(str(e))
                        )

    async def _call_async(self, tool_name, arguments):
        if not self._connected or self.session is None:
            raise RuntimeError(f"MCP client '{self.name}' not connected")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._command_queue.put((tool_name, arguments, future))
        return await future

    def call_tool(self, tool_name, arguments):
        if not self.is_connected():
            self.connect()

        timeout = float(self.config.get("call_timeout", 60))
        try:
            return self.bridge.run_coro(
                self._call_async(tool_name, arguments),
                timeout=timeout,
            )
        except Exception as first_err:
            err_lower = str(first_err).lower()
            if not self.is_connected() or "connection lost" in err_lower or "not connected" in err_lower:
                logger.warning(
                    f"MCP: reconnecting server '{self.name}' and retrying tool '{tool_name}'..."
                )
                self.connect()
                return self.bridge.run_coro(
                    self._call_async(tool_name, arguments),
                    timeout=timeout,
                )
            raise

    def close(self):
        self._connected = False
        if self._task is not None and self.bridge.is_started():
            try:
                self.bridge.run_coro(self._stop_existing_task(), timeout=5)
            except Exception:
                pass
        self._task = None
        self.session = None

    def is_connected(self):
        return bool(
            self._connected
            and self.session is not None
            and self._task is not None
            and not self._task.done()
        )