import logging
import sys
from pathlib import Path
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
    log_path = Path(CONFIG["LOG_FILE"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(file_handler)
except Exception as exc:
    logger.exception("Failed to configure file logging: %s", exc)


def log_unhandled_exception(exc_type, exc_value, exc_traceback):
    """Send uncaught exceptions to the shared Jarvis logger."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = log_unhandled_exception
