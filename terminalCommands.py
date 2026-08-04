import subprocess
import os
import tempfile
import threading
import time
import queue
import platform
import re
import sys
import shlex
import ast

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
    return True

def _is_system_destroyer(command: str) -> bool:
    if not command or not command.strip():
        return False
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        cmd_lower = command.lower()
        if re.search(r'\brm\s+-rf\s+/*\s*$', cmd_lower) or re.search(r'\bdel\s+/[fs]\s+c:\\', cmd_lower):
            return True
        return False
    if not tokens:
        return False
    cmd = tokens[0].lower()
    if cmd in ['format', 'diskpart', 'mkfs', 'fdisk', 'parted']:
        return True
    if cmd == 'dd':
        for token in tokens:
            if token.startswith('of=') or token.startswith('if='):
                if '/dev/sd' in token or '/dev/nvme' in token or '/dev/hd' in token or '\\\\.\\PhysicalDrive' in token:
                    return True
        return False
    if cmd in ['rm', 'del', 'rd', 'rmdir', 'erase']:
        has_force_recursive = False
        if platform.system() == 'Windows':
            if '/s' in tokens or '/q' in tokens:
                has_force_recursive = True
        else:
            if '-rf' in tokens or '-fr' in tokens or ('--recursive' in tokens and '--force' in tokens) or ('-r' in tokens and '-f' in tokens):
                has_force_recursive = True
        if not has_force_recursive:
            return False
        targets = []
        for token in tokens[1:]:
            if not token.startswith('-'):
                targets.append(token)
        if not targets:
            if command.strip().endswith('/') or command.strip().endswith('/*'):
                return True
            return False
        for target in targets:
            try:
                abs_path = os.path.realpath(target)
            except Exception:
                continue
            if platform.system() == 'Windows':
                if abs_path in ['C:\\', 'C:\\Windows', 'C:\\System32', 'D:\\', 'E:\\']:
                    return True
                if any(abs_path.startswith(drive) for drive in ['C:\\Windows', 'C:\\System32']):
                    return True
            else:
                if abs_path == '/' or abs_path == '/boot' or abs_path == '/etc' or abs_path == '/usr' or abs_path == '/bin' or abs_path == '/sbin' or abs_path == '/lib' or abs_path == '/dev':
                    return True
        return False
    return False

def _is_python_destructive(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    
    dangerous_patterns = [
        r'rm\s+-rf\s+/*', r'del\s+/[fs]\s+c:\\', r'format\s+[a-z]:',
        r'dd\s+.*of=/dev/sd', r'mkfs', r'diskpart', r'fdisk'
    ]
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                elif isinstance(node.func.value, ast.Attribute):
                    func_name = f"{ast.unparse(node.func.value)}.{node.func.attr}"
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
            
            if func_name:
                if func_name in ['os.system', 'os.popen', 'subprocess.run', 'subprocess.Popen', 'subprocess.call', 'subprocess.check_output']:
                    if node.args:
                        cmd_arg = None
                        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            cmd_arg = node.args[0].value
                        elif isinstance(node.args[0], ast.Str):
                            cmd_arg = node.args[0].s
                        if cmd_arg:
                            for pattern in dangerous_patterns:
                                if re.search(pattern, cmd_arg, re.IGNORECASE):
                                    return True
                
                if func_name in ['shutil.rmtree', 'os.remove', 'os.unlink', 'os.rmdir', 'shutil.move', 'shutil.copy']:
                    target_path = None
                    if node.args:
                        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            target_path = node.args[0].value
                        elif isinstance(node.args[0], ast.Str):
                            target_path = node.args[0].s
                    if target_path:
                        try:
                            abs_path = os.path.realpath(target_path)
                        except Exception:
                            continue
                        if platform.system() == 'Windows':
                            if abs_path in ['C:\\', 'C:\\Windows', 'C:\\System32'] or abs_path.startswith('C:\\Windows') or abs_path.startswith('C:\\System32'):
                                return True
                        else:
                            if abs_path == '/' or abs_path == '/boot' or abs_path == '/etc' or abs_path == '/usr' or abs_path == '/bin' or abs_path == '/sbin' or abs_path == '/lib' or abs_path == '/dev':
                                return True
                
                if func_name == 'open':
                    if len(node.args) > 1:
                        mode_arg = None
                        if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                            mode_arg = node.args[1].value.lower()
                        elif isinstance(node.args[1], ast.Str):
                            mode_arg = node.args[1].s.lower()
                        if mode_arg and ('w' in mode_arg or 'a' in mode_arg):
                            target_path = None
                            if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                target_path = node.args[0].value
                            elif isinstance(node.args[0], ast.Str):
                                target_path = node.args[0].s
                            if target_path:
                                try:
                                    abs_path = os.path.realpath(target_path)
                                except Exception:
                                    continue
                                if platform.system() == 'Windows':
                                    if abs_path.startswith('C:\\Windows') or abs_path.startswith('C:\\System32'):
                                        return True
                                else:
                                    if abs_path.startswith('/etc') or abs_path.startswith('/usr') or abs_path.startswith('/bin') or abs_path.startswith('/sbin') or abs_path.startswith('/lib') or abs_path.startswith('/dev'):
                                        return True
    return False

def is_python_code_safe(code: str) -> bool:
    if _is_python_destructive(code):
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
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            shell=False,
            cwd=user_home,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        self.output_queue = queue.Queue()
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()
        self._read_until_empty(timeout=0.5)

    def _read_output(self):
        for line in iter(self.process.stdout.readline, ''):
            self.output_queue.put(line)

    def _read_until_empty(self, timeout=0.5):
        lines = []
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                line = self.output_queue.get(timeout=0.1)
                if line:
                    lines.append(line)
                    end_time = time.time() + timeout
            except queue.Empty:
                pass
        return "".join(lines)

    def execute(self, command: str, timeout: int = 30) -> str:
        marker = f"__CMD_END_{time.time()}__"
        full_command = f"{command}\necho {marker}\n"
            
        self.process.stdin.write(full_command)
        self.process.stdin.flush()
        
        lines = []
        start_time = time.time()
        idle_timeout = 2.0
        last_output_time = time.time()
        end_time = start_time + timeout
        
        while time.time() < end_time:
            try:
                line = self.output_queue.get(timeout=0.1)
                if marker in line:
                    break
                if line:
                    lines.append(line)
                    last_output_time = time.time()
                else:
                    continue
            except queue.Empty:
                if time.time() - last_output_time > idle_timeout:
                    break
                continue
        
        output = "".join(lines).strip()
        
        MAX_OUTPUT_LENGTH = 50000
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:25000] + "\n\n... [OUTPUT TRUNCATED BY SYSTEM TO SAVE CONTEXT] ...\n\n" + output[-25000:]
            
        return output

terminal_session = StatefulTerminal()

def execute_terminal_command(command: str, timeout_seconds: int = 30) -> str:
    if _is_system_destroyer(command):
        print(f"\n\033[91m[SYSTEM PROTECTION]\033[0m Auto-blocked lethal command: {command}")
        return "Observation: 🚫 CRITICAL SYSTEM PROTECTION ACTIVE. Command targets system core and was automatically blocked. No execution took place."
    
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
        print(f"\n\033[91m[SYSTEM PROTECTION]\033[0m Auto-blocked lethal Python code.")
        return "Observation: 🚫 CRITICAL SYSTEM PROTECTION ACTIVE. Python code targets system core and was automatically blocked. No execution took place."
    else:
        print(f"\n\033[94m[AUTO-APPROVED PYTHON SCRIPT]\033[0m: Executing script...")
        
    fd, temp_path = tempfile.mkstemp(suffix=".py")
    
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(code_string)
            
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        python_path = sys.executable
            
        result = subprocess.run(
            [python_path, temp_path], 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=120
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        full_output = ""
        if output:
            full_output += f"Output:\n{output}\n"
        if error:
            full_output += f"Error:\n{error}\n"
            
        MAX_OUTPUT_LENGTH = 50000
        if len(full_output) > MAX_OUTPUT_LENGTH:
            full_output = full_output[:25000] + "\n\n... [TRUNCATED] ...\n\n" + full_output[-25000:]
            
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