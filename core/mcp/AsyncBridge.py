import asyncio
import sys
import threading


class AsyncBridge:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._started = False
        self._lock = threading.RLock()
        self._ready = threading.Event()

    def start(self):
        with self._lock:
            if self._started and self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="MCPAsyncBridge",
            )
            self._started = True
            self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass

    def is_started(self):
        with self._lock:
            return (
                self._started
                and self._loop is not None
                and not self._loop.is_closed()
                and self._thread is not None
                and self._thread.is_alive()
            )

    def run_coro(self, coro, timeout=30):
        if not self.is_started():
            self.start()
        with self._lock:
            loop = self._loop
            started = self._started
        if not started or loop is None or loop.is_closed():
            raise RuntimeError("AsyncBridge is not running")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def stop(self):
        with self._lock:
            if not self._started:
                return
            loop = self._loop
            thread = self._thread
            self._started = False
            self._loop = None
            self._thread = None
            self._ready.clear()
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=4)