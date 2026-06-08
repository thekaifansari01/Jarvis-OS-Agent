import logging
import sys
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme
from core.brain.config import CONFIG

jarvis_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "critical": "bold white on red",
    "success": "bold green"
})

console = Console(theme=jarvis_theme)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(console=console, rich_tracebacks=True, markup=True, show_path=False)
    ]
)

logger = logging.getLogger("rich")

try:
    file_handler = logging.FileHandler(CONFIG["LOG_FILE"], encoding='utf-8')
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)
except Exception:
    pass