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
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect, QParallelAnimationGroup, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect, QTextEdit, QPushButton
from PyQt5.QtGui import QFont, QColor, QFontDatabase
from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY, GROQ_FAST_MODEL
from groq import Groq

def _fallback_analysis(content: str) -> str:
    reasons = []
    content_lower = content.lower()
    
    if any(x in content_lower for x in ["subprocess", "os.system", "os.popen"]):
        reasons.append("• Yeh script background me OS-level commands execute kar rahi hai.")
    if any(x in content_lower for x in ["shutil.rmtree", "os.remove", "os.rmdir", "del ", "rm "]):
        reasons.append("• ⚠️ DANGER: Yeh script local files ya folders ko delete/modify kar rahi hai.")
    if any(x in content_lower for x in ["requests", "urllib", "curl", "wget"]):
        reasons.append("• Yeh script external network ya internet se data fetch/download kar rahi hai.")
    if "open(" in content_lower and ("'w'" in content_lower or '"w"' in content_lower):
        reasons.append("• Yeh script naye files bana rahi hai ya existings files overwrite kar rahi hai.")
    if any(x in content_lower for x in ["format ", "diskpart", "mkfs"]):
        reasons.append("• 🚨 CRITICAL: Yeh command directly aapke disk partitions ko target kar rahi hai.")
        
    if not reasons:
        reasons.append("• Yeh ek complex payload hai jo system resources access kar raha hai. Kripya review karein.")
        
    return "Fast Brain Assessment (Fallback):\n" + "\n".join(reasons)

class SecurityDialog(QDialog):
    analysis_ready = pyqtSignal(str)

    def __init__(self, action_type, content):
        super().__init__()
        self.action_type = action_type
        self.content = content
        self.approved = False

        eng_id = QFontDatabase.addApplicationFont("Data/fonts/english.ttf")
        eng_fams = QFontDatabase.applicationFontFamilies(eng_id)
        self.font_eng = eng_fams[0] if eng_fams else "Segoe UI"
        
        self.initUI()
        self.analysis_ready.connect(self.update_analysis_text)
        threading.Thread(target=self.run_llm, daemon=True).start()

    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(680, 600)

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(20, 20, 20, 20)

        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.15),
                    stop:0.35 rgba(255, 255, 255, 0.05),
                    stop:0.75 rgba(220, 38, 38, 0.15),
                    stop:1 rgba(255, 255, 255, 0.1)
                );
                border-radius: 28px;
            }
        """)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(50)
        self.shadow.setColor(QColor(0, 0, 0, 180))
        self.shadow.setOffset(0, 12)
        self.container.setGraphicsEffect(self.shadow)

        self.wrapper_layout = QVBoxLayout(self.container)
        self.wrapper_layout.setContentsMargins(1, 1, 1, 1)

        self.inner_island = QFrame(self.container)
        self.inner_island.setStyleSheet("""
            QFrame {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(15, 23, 42, 0.98), 
                    stop:0.45 rgba(10, 15, 28, 0.99),
                    stop:1 rgba(2, 6, 23, 1.0)
                );
                border-radius: 27px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        self.wrapper_layout.addWidget(self.inner_island)

        self.layout = QVBoxLayout(self.inner_island)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(15)

        badge = QLabel(" CRITICAL EXECUTION BLOCKED ")
        badge.setFont(QFont(self.font_eng, 8, QFont.Bold))
        badge.setStyleSheet("background: #ef4444; color: white; border-radius: 4px; padding: 2px 6px;")
        badge.setFixedSize(badge.sizeHint())
        self.layout.addWidget(badge)

        title_lbl = QLabel(self.action_type)
        title_lbl.setFont(QFont(self.font_eng, 14, QFont.Bold))
        title_lbl.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        self.layout.addWidget(title_lbl)

        desc_lbl = QLabel("Review the requested system action before granting execution permission:")
        desc_lbl.setFont(QFont(self.font_eng, 10))
        desc_lbl.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        self.layout.addWidget(desc_lbl)

        self.code_box = QTextEdit()
        self.code_box.setReadOnly(True)
        self.code_box.setPlainText(self.content)
        self.code_box.setFont(QFont("Consolas", 10))
        self.code_box.setStyleSheet("""
            QTextEdit {
                background-color: #020617;
                color: #38bdf8;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                padding: 10px;
            }
        """)
        self.layout.addWidget(self.code_box)

        analysis_frame = QFrame()
        analysis_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        af_layout = QVBoxLayout(analysis_frame)
        af_layout.setContentsMargins(15, 12, 15, 12)

        analysis_title = QLabel("🛡️ AI Security Assessment")
        analysis_title.setFont(QFont(self.font_eng, 10, QFont.Bold))
        analysis_title.setStyleSheet("color: #f59e0b; background: transparent; border: none;")
        af_layout.addWidget(analysis_title)

        self.analysis_lbl = QLabel("Jarvis Neural Security: Analyzing payload for system risks...")
        self.analysis_lbl.setFont(QFont(self.font_eng, 9))
        self.analysis_lbl.setStyleSheet("color: #cbd5e1; background: transparent; border: none;")
        self.analysis_lbl.setWordWrap(True)
        af_layout.addWidget(self.analysis_lbl)

        self.layout.addWidget(analysis_frame)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 10, 0, 0)
        btn_layout.addStretch()

        self.btn_deny = QPushButton("❌ Deny & Block")
        self.btn_deny.setFont(QFont(self.font_eng, 10, QFont.Bold))
        self.btn_deny.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; border-radius: 8px; padding: 8px 20px;
            }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.btn_deny.clicked.connect(self.on_deny)
        btn_layout.addWidget(self.btn_deny)

        self.btn_approve = QPushButton("✅ Approve & Execute")
        self.btn_approve.setFont(QFont(self.font_eng, 10, QFont.Bold))
        self.btn_approve.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; color: white; border-radius: 8px; padding: 8px 20px;
            }
            QPushButton:hover { background-color: #15803d; }
        """)
        self.btn_approve.clicked.connect(self.on_approve)
        btn_layout.addWidget(self.btn_approve)

        self.layout.addLayout(btn_layout)
        self.outer_layout.addWidget(self.container)

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.setGeometry(x, y - 40, self.width(), self.height())
        self.setWindowOpacity(0.0)

        self.anim_group = QParallelAnimationGroup(self)
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(300)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        slide_down = QPropertyAnimation(self, b"pos")
        slide_down.setDuration(400)
        slide_down.setStartValue(QPoint(x, y - 40))
        slide_down.setEndValue(QPoint(x, y))
        slide_down.setEasingCurve(QEasingCurve.OutCubic)

        self.anim_group.addAnimation(fade_in)
        self.anim_group.addAnimation(slide_down)
        self.anim_group.start()

    def run_llm(self):
        if not GROQ_API_KEY:
            self.analysis_ready.emit(_fallback_analysis(self.content))
            return
        try:
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                "You are Jarvis's Neural Security module. Analyze the provided python/terminal payload "
                "and explain it to the user in natural, conversational Hinglish (Roman script) using 2-3 concise bullet points.\n\n"
                "CRITICAL RULES:\n"
                "1. Explain exactly what the script is trying to do.\n"
                "2. Be objective & calm: Do not unnecessarily scare the user if it is a normal/safe command (like ping, tasklist, reading files, or system info). Just explain that it was intercepted because it requires OS-level execution.\n"
                "3. If it is genuinely destructive or suspicious (deleting files, formatting, unauthorized network downloads), warn the user clearly.\n"
                "4. Start directly with the bullet points (e.g., '• Yeh script...'). Do not provide any code or English filler text."
            )
            response = client.chat.completions.create(
                model=GROQ_FAST_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Code:\n{self.content}"}
                ],
                temperature=0.1,
                max_tokens=150
            )
            self.analysis_ready.emit(f"Fast Brain Assessment:\n{response.choices[0].message.content.strip()}")
        except Exception:
            self.analysis_ready.emit(_fallback_analysis(self.content))

    def update_analysis_text(self, text):
        self.analysis_lbl.setText(text)
        self.analysis_lbl.setStyleSheet("color: #38bdf8; background: transparent; border: none;")

    def on_approve(self):
        self.approved = True
        self.accept()

    def on_deny(self):
        self.approved = False
        self.reject()

def get_user_approval(action_type: str, content: str) -> bool:
    logger.warning(f"[JARVIS REQUESTS CRITICAL PERMISSION]")
    logger.warning(f"Action: {action_type}")

    if not QApplication.instance():
        _app = QApplication(sys.argv)
    
    dialog = SecurityDialog(action_type, content)
    dialog.exec_()

    if dialog.approved:
        logger.info("[USER APPROVED] Executing critical payload.")
        return True
    else:
        logger.warning("[USER DENIED] Payload blocked.")
        return False

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
        if not get_user_approval("Terminal Command Execution (CRITICAL)", command):
            return "Observation: Action Denied by User."

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
        logger.info("[AUTO-APPROVED PYTHON SCRIPT]: Executing safe data/processing script...")

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

