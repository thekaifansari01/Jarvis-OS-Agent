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
import tkinter as tk
from tkinter import scrolledtext
from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY, GROQ_FAST_MODEL
from groq import Groq

def _fallback_analysis(content: str) -> str:
    reasons = []
    content_lower = content.lower()
    if any(x in content_lower for x in ["subprocess", "os.system", "os.popen"]):
        reasons.append("- Executes hidden OS-level commands.")
    if any(x in content_lower for x in ["shutil.rmtree", "os.remove", "os.rmdir", "del ", "rm "]):
        reasons.append("- Modifies or permanently deletes files/directories.")
    if "requests" in content_lower or "urllib" in content_lower:
        reasons.append("- Makes external network connections.")
    if "open(" in content_lower and ("'w'" in content_lower or '"w"' in content_lower):
        reasons.append("- Overwrites or writes new local files.")
    if "format " in content_lower or "diskpart" in content_lower:
        reasons.append("- Modifies disk partitions.")
    if not reasons:
        reasons.append("- Performs potentially unsafe system modifications.")
    return "Fallback Security Analysis:\n" + "\n".join(reasons)

def _llm_analyze(content: str, ui_callback):
    if not GROQ_API_KEY:
        ui_callback(_fallback_analysis(content))
        return
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = "You are a cyber security expert. Analyze the following python/terminal payload. Explain in 2-3 concise bullet points what this script does and why it was flagged as risky. Do not provide code, just the risk analysis in plain text."
        response = client.chat.completions.create(
            model=GROQ_FAST_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Code:\n{content}"}
            ],
            temperature=0.1,
            max_tokens=150
        )
        analysis = response.choices[0].message.content.strip()
        ui_callback(f"Fast Brain Assessment:\n{analysis}")
    except Exception:
        ui_callback(_fallback_analysis(content))

def get_user_approval(action_type: str, content: str) -> bool:
    logger.warning(f"[JARVIS REQUESTS CRITICAL PERMISSION]")
    logger.warning(f"Action: {action_type}")

    root = tk.Tk()
    root.title(f"Jarvis Security Intercept — {action_type}")
    root.geometry("680x580")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg="#0f172a")
    root.eval('tk::PlaceWindow . center')

    approval_result = [False]

    def on_approve():
        approval_result[0] = True
        root.quit()
        root.destroy()

    def on_deny():
        approval_result[0] = False
        root.quit()
        root.destroy()

    main_frame = tk.Frame(root, bg="#0f172a", padx=25, pady=20)
    main_frame.pack(fill="both", expand=True)

    header_frame = tk.Frame(main_frame, bg="#0f172a")
    header_frame.pack(fill="x", pady=(0, 12))

    badge = tk.Label(header_frame, text=" CRITICAL EXECUTION BLOCKED ", font=("Segoe UI", 8, "bold"), bg="#ef4444", fg="white", padx=8, pady=3)
    badge.pack(anchor="w")

    title_lbl = tk.Label(header_frame, text=action_type, font=("Segoe UI", 13, "bold"), bg="#0f172a", fg="#f8fafc", pady=4)
    title_lbl.pack(anchor="w")

    desc_lbl = tk.Label(header_frame, text="Review the requested system action before granting execution permission:", font=("Segoe UI", 9), bg="#0f172a", fg="#94a3b8")
    desc_lbl.pack(anchor="w")

    code_frame = tk.Frame(main_frame, bg="#1e293b", padx=1, pady=1)
    code_frame.pack(fill="x", pady=(0, 15))

    # FIXED: Changed font size 9.5 to 10
    code_box = scrolledtext.ScrolledText(code_frame, height=9, font=("Consolas", 10), bg="#020617", fg="#38bdf8", relief="flat", bd=0, insertbackground="white")
    code_box.pack(fill="both", expand=True, padx=6, pady=6)
    code_box.insert(tk.END, content)
    code_box.configure(state='disabled')

    analysis_frame = tk.Frame(main_frame, bg="#1e293b", padx=15, pady=12)
    analysis_frame.pack(fill="x", pady=(0, 20))

    # FIXED: Changed font size 9.5 to 10
    analysis_title = tk.Label(analysis_frame, text="🛡️ AI Security Assessment", font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#f59e0b")
    analysis_title.pack(anchor="w", pady=(0, 4))

    analysis_lbl = tk.Label(analysis_frame, text="Jarvis Neural Security: Analyzing payload for system risks...", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1", justify="left", wraplength=580, anchor="w")
    analysis_lbl.pack(anchor="w", fill="x")

    def update_ui(text):
        root.after(0, lambda: analysis_lbl.config(text=text, fg="#38bdf8"))

    threading.Thread(target=_llm_analyze, args=(content, update_ui), daemon=True).start()

    btn_frame = tk.Frame(main_frame, bg="#0f172a")
    btn_frame.pack(fill="x", side="bottom")

    # FIXED: Changed font size 9.5 to 10
    btn_deny = tk.Button(btn_frame, text="❌ Deny & Block", font=("Segoe UI", 10, "bold"), bg="#dc2626", fg="white", activebackground="#b91c1c", activeforeground="white", relief="flat", bd=0, padx=20, pady=8, cursor="hand2", command=on_deny)
    btn_deny.pack(side="right", padx=(10, 0))

    # FIXED: Changed font size 9.5 to 10
    btn_approve = tk.Button(btn_frame, text="✅ Approve & Execute", font=("Segoe UI", 10, "bold"), bg="#16a34a", fg="white", activebackground="#15803d", activeforeground="white", relief="flat", bd=0, padx=20, pady=8, cursor="hand2", command=on_approve)
    btn_approve.pack(side="right")

    root.protocol("WM_DELETE_WINDOW", on_deny)
    root.mainloop()

    if approval_result[0]:
        logger.info("[USER APPROVED] Executing critical payload.")
    else:
        logger.warning("[USER DENIED] Payload blocked.")
    return approval_result[0]

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

def is_python_code_safe(code: str) -> bool:
    dangerous_patterns = [
        r'subprocess',
        r'os\.system',
        r'os\.popen',
        r'shutil\.rmtree',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
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

    heavy_keywords = ['pip install', 'npm install', 'npm i ', 'git clone', 'yarn add', 'pnpm install', 'apt-get install']
    if any(kw in command.lower() for kw in heavy_keywords) and timeout_seconds <= 30:
        timeout_seconds = 180
        logger.warning(f"[HEAVY COMMAND DETECTED]: Auto-extending terminal timeout to {timeout_seconds} seconds.")

    logger.info(f"[AUTO-APPROVED TERMINAL COMMAND]: {command}")
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
        logger.info("[AUTO-APPROVED PYTHON SCRIPT]: Executing data processing script...")

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