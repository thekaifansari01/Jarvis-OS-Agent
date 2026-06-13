import logging
import os
import sys
import re
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


def print_jarvis_output(response_text):
    """Jarvis ke final output ko ek premium Markdown panel mein render karta hai."""
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

def print_user_input(command):
    """User input ko cleanly dikhane ke liye."""
    console.print(f"\n[user]❯ {command}[/user]")

def get_spinner(text="Processing..."):
    """
    Main loop mein use karne ke liye live spinner.
    Use case: 
    with get_spinner("Routing to Fast Brain..."):
        # do work
    """
    return console.status(f"[bold {CLAUDE_COLOR}]{text}[/]", spinner="dots2")



class MinimalistFilter(logging.Filter):
    """Faltu aur system noise ko hide karta hai taaki terminal clean rahe."""
    def filter(self, record):
        msg = record.getMessage()
        noisy_patterns = [
            "HTTP Request:", "batchEmbedContents", "gemini-embedding",
            "ChromaDB", "collections cleared", "AFC is enabled",
            "file_cache is only supported", "INFO:", "DEBUG:"
        ]
        return not any(pattern in msg for pattern in noisy_patterns)

class MinimalistFormatter(logging.Formatter):
    """Tere backend logs ko pakad kar Anthropic CLI style mein tree-format karega."""
    def format(self, record):
        msg = record.getMessage()
        if not msg: return ""

        msg = re.sub(r'\x1b\[.*?m', '', msg)

        if "You said:" in msg:
            cmd = msg.split("You said:")[-1].strip()
            return f"\n[user]❯ {cmd}[/user]"
            
        elif "JARVIS:" in msg:
            resp = msg.split("JARVIS:")[-1].strip()
            return f"\n[claude]Jarvis[/claude]\n{resp}\n"
            
        elif "Routing to Fast Brain" in msg:
            return f"  [system]⠧ Routing to Fast Brain...[/system]"
            
        elif "AGENTIC LOOP INITIATED" in msg:
            return f"\n  [claude]▶ Initiating Agentic Loop[/claude]"
        elif "Agent Thought:" in msg:
            thought = msg.split("Agent Thought:")[-1].strip()
            return f"  [system]│ 💭 Thinking: {thought}[/system]"
        elif "Agent executing" in msg:
            act = msg.split("Agent executing")[-1].strip()
            return f"  [system]│ ⚙️ Tool: {act}[/system]"
        elif "🤖 Agent" in msg:
            act = msg.replace("🤖 Agent", "").strip()
            return f"  [system]│ ⚙️ Action: {act}[/system]"
        elif "Observation:" in msg:
            obs = msg.split("Observation:")[-1].strip()
            if len(obs) > 130: 
                obs = obs[:127] + "..."
            return f"  [system]│ ↳ {obs}[/system]"
        elif "Agent declared task complete" in msg:
            return f"  [success]  ✓ Task Complete[/success]"
            
        elif "Wake word" in msg: 
            return f"\n[claude]▶[/claude] [system]System wake signal detected...[/system]"
        elif "Listening" in msg: 
            return f"[claude]▶[/claude] [system]Listening stream active...[/system]"
            
        elif "❌" in msg or "Error" in msg or "failed" in msg.lower():
            clean_msg = msg.replace("❌", "").strip()
            return f"  [error]│ ❌ {clean_msg}[/error]"
            
        else:
            clean_msg = msg.replace("🤖", "").replace("⚡", "").strip()
            return f"  [system]• {clean_msg}[/system]"

def print_banner():
    """Claude CLI style minimalist static banner."""
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
    console.print(f"  [bold {CLAUDE_COLOR}]Jarvis Core v3.1[/bold {CLAUDE_COLOR}] [system]— Mindly AI Agent[/system]")
    console.print("  [system]Awaiting terminal input or voice command...[/system]\n")

def disable_quickedit():
    """Windows CMD ko click karne par freeze hone se rokta hai."""
    if os.name != 'nt': return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value &= ~0x0040
        kernel32.SetConsoleMode(handle, mode)
    except: pass

def setup_premium_terminal():
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
    rich_handler.addFilter(MinimalistFilter())
    rich_handler.setFormatter(MinimalistFormatter())
    
    root_logger.addHandler(rich_handler)
    
    for lib in ['urllib3', 'requests', 'google', 'http', 'asyncio', 'chromadb']:
        logging.getLogger(lib).setLevel(logging.WARNING)

def init_terminal():
    """Call this in main.py to launch the interface."""
    if os.name == 'nt':
        os.system('chcp 65001 > nul')
    disable_quickedit()
    setup_premium_terminal()
    print_banner()