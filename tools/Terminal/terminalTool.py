import subprocess
import os
import tempfile
import threading
import time
import queue
import platform
import re

def get_user_approval(action_type: str, content: str) -> bool:
    print(f"\n\033[91m[JARVIS REQUESTS CRITICAL PERMISSION]\033[0m")
    print(f"Action: {action_type}")
    print(f"Content:\n{content}\n")
    
    while True:
        choice = input("\033[92mAllow execution? (Y/N):\033[0m ").strip().upper()
        if choice == 'Y':
            return True
        elif choice == 'N':
            return False
        print("Invalid input. Please enter Y or N.")

def is_terminal_command_safe(command: str) -> bool:
    dangerous_patterns = [
        r'\bdel\b', r'\brm\b', r'\brmdir\b', r'\bmkdir\b', r'\bmd\b', r'\bmove\b', 
        r'\bren\b', r'\brename\b', r'\bformat\b', r'\bcopy\b', r'\bcp\b', r'\bmv\b',
        r'\bRemove-Item\b', r'\bNew-Item\b', r'\bMove-Item\b', r'\bRename-Item\b', r'\bCopy-Item\b',
        r'\bSet-Content\b', r'\bAdd-Content\b', r'\bClear-Content\b', 
        r'\bwget\b', r'\bcurl\b', r'\bInvoke-WebRequest\b', r'\bpip install\b', r'\bnpm install\b',
        r'\bgit clone\b', r'\bvenv\b', r'\bnpm\b',
        r'>', r'>>'
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    return True

def is_python_code_safe(code: str) -> bool:
    dangerous_patterns = [
        r'os\.remove', r'os\.rmdir', r'os\.unlink', r'os\.mkdir', r'os\.makedirs',
        r'shutil\.rmtree', r'shutil\.move', r'shutil\.copy',
        r'open\s*\([^,]+,\s*[\'"][wa]b?[\'"]\)', 
        r'subprocess', r'os\.system', r'os\.popen'
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            return False
    return True

class StatefulTerminal:
    def __init__(self):
        shell_cmd = "cmd.exe" if platform.system() == "Windows" else "/bin/bash"
        user_home = os.path.expanduser("~")
        self.process = subprocess.Popen(
            shell_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
            cwd=user_home
        )
        self.output_queue = queue.Queue()
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()
        self._read_until_empty(timeout=0.5)

    def _read_output(self):
        for line in iter(self.process.stdout.readline, ''):
            self.output_queue.put(line)

    def _read_until_empty(self, timeout=0.2):
        lines = []
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                line = self.output_queue.get(timeout=0.1)
                lines.append(line)
                end_time = time.time() + timeout 
            except queue.Empty:
                pass
        return "".join(lines)

    def execute(self, command: str, timeout: int = 30) -> str:
        marker = f"__CMD_END_{time.time()}__"
        if platform.system() == "Windows":
            full_command = f"{command}\necho {marker}\n"
        else:
            full_command = f"{command}\necho {marker}\n"
            
        self.process.stdin.write(full_command)
        self.process.stdin.flush()
        
        lines = []
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                line = self.output_queue.get(timeout=0.1)
                if marker in line:
                    break
                lines.append(line)
            except queue.Empty:
                continue
        
        output = "".join(lines).strip()
        
        if len(output) > 3000:
            output = output[:1500] + "\n\n... [OUTPUT TRUNCATED BY SYSTEM TO SAVE CONTEXT] ...\n\n" + output[-1500:]
            
        return output

terminal_session = StatefulTerminal()

def execute_terminal_command(command: str, timeout_seconds: int = 30) -> str:
    if not is_terminal_command_safe(command):
        if not get_user_approval("Terminal Command (CRITICAL)", command):
            return "Observation: Action Denied by User."
    else:
        print(f"\n\033[94m[AUTO-APPROVED TERMINAL COMMAND]\033[0m: {command}")
    
    try:
        output = terminal_session.execute(command, timeout=timeout_seconds)
        if output:
            return f"Observation: Command executed.\nOutput:\n{output}"
        return "Observation: Command executed successfully with no output."
    except Exception as e:
        return f"Observation: Terminal execution crashed -> {str(e)}"

def run_python_code(code_string: str) -> str:
    if not is_python_code_safe(code_string):
        if not get_user_approval("Python Code Execution (CRITICAL)", code_string):
            return "Observation: Action Denied by User."
    else:
        print(f"\n\033[94m[AUTO-APPROVED PYTHON SCRIPT]\033[0m: Executing data processing script...")
        
    fd, temp_path = tempfile.mkstemp(suffix=".py")
    
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(code_string)
            
        result = subprocess.run(
            ["python", temp_path], 
            capture_output=True, 
            text=True, 
            timeout=120
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        full_output = ""
        if output:
            full_output += f"Output:\n{output}\n"
        if error:
            full_output += f"Error:\n{error}\n"
            
        if len(full_output) > 3000:
            full_output = full_output[:1500] + "\n\n... [TRUNCATED] ...\n\n" + full_output[-1500:]
            
        if result.returncode == 0:
            return f"Observation: Python code executed successfully.\n{full_output}"
        else:
            return f"Observation: Python script failed.\n{full_output}"
            
    except subprocess.TimeoutExpired:
        return "Observation: Python script timed out after 120 seconds."
    except Exception as e:
        return f"Observation: Python execution crashed -> {str(e)}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)