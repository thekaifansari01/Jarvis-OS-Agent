import logging
import os
import re
import ctypes
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.panel import Panel
from rich.markdown import Markdown

CLAUDE_COLOR = "#d87856"

custom_theme = Theme({
    "claude": CLAUDE_COLOR,
    "user": "bold white",
    "system": "dim white",
    "success": "bold green",
    "error": "bold red"
})

console = Console(theme=custom_theme)

def print_jarvis_output(response_text: str) -> None:
    """Render Jarvis final response in a clean Markdown panel."""
    md = Markdown(response_text)
    panel = Panel(
        md,
        title=f"[bold {CLAUDE_COLOR}]🤖 Jarvis[/]",
        border_style=CLAUDE_COLOR,
        expand=False,
        padding=(1, 2)
    )
    console.print(panel)
    console.print()


def print_user_input(command: str) -> None:
    """Show user command clearly."""
    console.print(f"\n[user]❯ {command}[/user]")


def get_spinner(text: str = "Processing..."):
    """Return a live spinner context manager."""
    return console.status(f"[bold {CLAUDE_COLOR}]{text}[/]", spinner="dots2")

class StrictFilter(logging.Filter):
    """Suppress all noisy library and internal logs."""
    def filter(self, record):
        msg = record.getMessage()
        noisy_patterns = [
            "HTTP Request:", "batchEmbedContents", "gemini-embedding",
            "ChromaDB", "collections cleared", "AFC is enabled",
            "file_cache", "ZMQ", "PUB", "SUB", "zmq", "PyQt",
            "QPainter", "setGeometry", "Unable to set geometry",
            "PIL", "pycaw", "comtypes", "urllib3", "requests",
            "Agent Panel", "STT Popup", "Baileys", "Proactive",
            "Memory Update", "AsyncBrowser", "loadResource",
            "reset_agent_status", "Step:", "THINKING", "TOOL",
            "Live feedback", "Flushed", "Tray icon", "reset",
            "Booting", "System initialization", "SessionCookies",
        ]
        return not any(p in msg for p in noisy_patterns)

class CleanFormatter(logging.Formatter):
    """Format logs as short single lines, no extra junk."""
    def format(self, record):
        msg = record.getMessage()
        if not msg:
            return ""

        msg = re.sub(r'\x1b\[.*?m', '', msg)

        if len(msg) > 100:
            msg = msg[:97] + "..."

        if "You said:" in msg:
            cmd = msg.split("You said:")[-1].strip()
            return f"\n[user]❯ {cmd}[/user]"

        if "JARVIS:" in msg:
            resp = msg.split("JARVIS:")[-1].strip()
            return f"\n[claude]Jarvis[/claude]\n{resp}\n"

        if "Agent Thought:" in msg:
            thought = msg.split("Agent Thought:")[-1].strip()
            return f"  [system]💭 {thought}[/system]"

        if "Observation:" in msg:
            obs = msg.split("Observation:")[-1].strip()
            if len(obs) > 100:
                obs = obs[:97] + "..."
            return f"  [system]↳ {obs}[/system]"

        if "❌" in msg or "Error" in msg or "failed" in msg.lower():
            clean_msg = msg.replace("❌", "").strip()
            return f"  [error]⚠️ {clean_msg}[/error]"

        return f"  [system]• {msg}[/system]"


def print_banner() -> None:
    """Display the startup banner."""
    os.system('cls' if os.name == 'nt' else 'clear')

    logo_raw = f"""
[{CLAUDE_COLOR}]       ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗[/{CLAUDE_COLOR}]
[{CLAUDE_COLOR}]       ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝[/{CLAUDE_COLOR}]
[{CLAUDE_COLOR}]       ██║███████║██████╔╝██║   ██║██║███████╗[/{CLAUDE_COLOR}]
[{CLAUDE_COLOR}]  ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║[/{CLAUDE_COLOR}]
[{CLAUDE_COLOR}]  ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║[/{CLAUDE_COLOR}]
[{CLAUDE_COLOR}]   ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝[/{CLAUDE_COLOR}]
"""

    console.print("\n" + logo_raw)
    console.print(f"  [bold {CLAUDE_COLOR}]Jarvis Core v3.1[/bold {CLAUDE_COLOR}] [system]— Clean Terminal[/system]")
    console.print("  [system]Ready.[/system]\n")

def disable_quickedit() -> None:
    """Prevent console freezing on Windows click."""
    if os.name != 'nt':
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value &= ~0x0040
        kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass


def setup_premium_terminal() -> None:
    """Configure logging with strict filters and clean formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    rich_handler = RichHandler(
        console=console,
        show_time=False,
        show_level=False,
        show_path=False,
        markup=True
    )
    rich_handler.addFilter(StrictFilter())
    rich_handler.setFormatter(CleanFormatter())

    root_logger.addHandler(rich_handler)

    for lib in [
        'urllib3', 'requests', 'google', 'http', 'asyncio', 'chromadb',
        'PIL', 'pycaw', 'comtypes', 'zmq', 'PyQt5', 'tavily'
    ]:
        logging.getLogger(lib).setLevel(logging.ERROR)


def init_terminal() -> None:
    """Main entry point – call once at startup."""
    if os.name == 'nt':
        os.system('chcp 65001 > nul')
    disable_quickedit()
    setup_premium_terminal()
    print_banner()