import atexit
import os
import platform
import subprocess
import time
import psutil
from typing import Optional

class SubprocessManager:
    _instance = None
    _children = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            atexit.register(cls._instance.cleanup)
        return cls._instance
    
    def spawn(self, args, **kwargs) -> Optional[subprocess.Popen]:
        if platform.system() == 'Windows':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True
        proc = subprocess.Popen(args, **kwargs)
        self._children.append(proc)
        return proc
    
    def kill_process_tree(self, pid: int):
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            _, alive = psutil.wait_procs(children, timeout=3)
            for p in alive:
                p.kill()
            parent.terminate()
            parent.wait(2)
        except psutil.NoSuchProcess:
            pass
    
    def cleanup(self):
        for proc in self._children:
            if proc.poll() is None:
                self.kill_process_tree(proc.pid)
        self._children.clear()

proc_manager = SubprocessManager()