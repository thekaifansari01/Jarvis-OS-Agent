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
from core.logger.logger import logger

def is_terminal_command_safe(command: str) -> bool:
    cmd_lower = command.lower()
    suspicious_patterns = [
        r'\bcurl\b', r'\bwget\b', r'\biwr\b', r'\binvoke-webrequest\b',
        r'\bssh\b', r'\bftp\b', r'\btelnet\b', r'\bnc\b', r'\bnetcat\b',
        r'\breg\s+add\b', r'\breg\s+delete\b', r'\bregedit\b',
        r'\btaskkill\b', r'\bkill\b', r'\bstop-process\b',
        r'\bchmod\b', r'\bchown\b', r'\bicacls\b', r'\btakeown\b',
        r'\bformat\b', r'\bdiskpart\b', r'\bvssadmin\b', r'\bwmic\b',
        r'\bnet\s+user\b', r'\bnet\s+localgroup\b'
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, cmd_lower):
            return False
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

def is_python_code_safe(code: str) -> bool:
    destructive_patterns = [
        r'shutil\.rmtree', r'os\.remove', r'os\.unlink', r'os\.rmdir',
        r'os\.rename', r'os\.replace', r'os\.chmod', r'os\.chown',
        r'winreg', r'__import__\([\'"]os[\'"]\)\.system',
        r'eval\(', r'exec\('
    ]
    for pattern in destructive_patterns:
        if re.search(pattern, code):
            return False
    os_exec_patterns = [r'subprocess', r'os\.system', r'os\.popen', r'os\.spawn']
    uses_os_exec = any(re.search(p, code) for p in os_exec_patterns)
    if uses_os_exec:
        risky_shell_words = [
            r'\brm\b', r'\bdel\b', r'\berase\b', r'\bformat\b', r'\bfdisk\b',
            r'\bmkfs\b', r'\bparted\b', r'\bkill\b', r'\btaskkill\b',
            r'\bshutdown\b', r'\breboot\b', r'\bpoweroff\b', r'\bcurl\b',
            r'\bwget\b', r'\biwr\b', r'\bchmod\b', r'\bchown\b', r'\battrib\b',
            r'\breg\b', r'\bnetsh\b', r'\bdiskpart\b', r'\bvssadmin\b',
            r'>', r'>>', r'\|'
        ]
        code_lower = code.lower()
        for risky in risky_shell_words:
            if re.search(risky, code_lower):
                return False
    return True

class StatefulTerminal:
    def __init__(self):
        shell_cmd = "cmd.exe" if platform.system() == "Windows" else "/bin/bash"
        user_home = os.path.expanduser("~")
        custom_env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PIP_PROGRESS_BAR": "off",
            "CI": "true",
            "NPM_CONFIG_PROGRESS": "false"
        }
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
            env=custom_env
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
        end_time = start_time + timeout
        while time.time() < end_time:
            try:
                line = self.output_queue.get(timeout=0.1)
                if marker in line:
                    break
                if line:
                    lines.append(line)
            except queue.Empty:
                continue
        output = "".join(lines).strip()
        MAX_OUTPUT_LENGTH = 50000
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:25000] + "\n\n... [OUTPUT TRUNCATED BY SYSTEM TO SAVE CONTEXT] ...\n\n" + output[-25000:]
        return output

terminal_session = StatefulTerminal()

def execute_terminal_command(command: str, timeout_seconds: int = 30) -> str:
    if _is_system_destroyer(command):
        logger.error(f"[SYSTEM PROTECTION] Auto-blocked lethal command: {command}")
        return "Observation: 🚫 CRITICAL SYSTEM PROTECTION ACTIVE. Command targets system core and was automatically blocked. No execution took place."

    if not is_terminal_command_safe(command):
        logger.warning(f"[SECURITY] Potentially unsafe command blocked: {command}")
        return "Observation: Command blocked for safety reasons. If you trust this command, modify the safety rules."

    if command.strip().lower().startswith("adb "):
        logger.info(f"[DIRECT ADB EXECUTION]: {command}")
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout_seconds,
                encoding='utf-8',
                errors='replace'
            )
            output = (result.stdout + "\n" + result.stderr).strip()
            if output:
                return f"Observation: Command executed.\nOutput:\n{output}"
            return "Observation: Command executed successfully with no output."
        except subprocess.TimeoutExpired:
            return f"Observation: ADB command timed out after {timeout_seconds} seconds."
        except Exception as e:
            return f"Observation: ADB execution crashed -> {str(e)}"

    heavy_keywords = ['pip install', 'npm install', 'npm i ', 'git clone', 'yarn add', 'pnpm install', 'apt-get install']
    if any(kw in command.lower() for kw in heavy_keywords) and timeout_seconds <= 30:
        timeout_seconds = 180
        logger.warning(f"[HEAVY COMMAND DETECTED]: Auto-extending terminal timeout to {timeout_seconds} seconds.")

    logger.info(f"[TERMINAL EXECUTION]: {command}")
    try:
        output = terminal_session.execute(command, timeout=timeout_seconds)
        if output:
            return f"Observation: Command executed.\nOutput:\n{output}"
        return "Observation: Command executed successfully with no output."
    except Exception as e:
        return f"Observation: Terminal execution crashed -> {str(e)}"

def run_python_code(code_string: str) -> str:
    if not is_python_code_safe(code_string):
        logger.warning(f"[SECURITY] Unsafe Python code blocked.")
        return "Observation: Python code blocked for safety reasons. If you trust this code, modify the safety rules."

    logger.info("[PYTHON EXECUTION]: Running Python script...")
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