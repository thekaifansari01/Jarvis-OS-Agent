import webbrowser
from pathlib import Path
from urllib.parse import urlparse, unquote
from typing import Tuple, List

from AppOpener import open as open_app
from core.logger.logger import logger

_ALLOWED_SCHEMES = ("http", "https", "file")


def resolve_to_url(target: str) -> str:
    if target is None:
        return ""

    raw = str(target).strip().strip('"').strip("'")
    if not raw:
        return ""

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()

    if scheme in ("http", "https"):
        return raw

    if scheme == "file":
        try:
            path_str = unquote(parsed.path)
            # Windows: "/C:/Users/..." → "C:/Users/..."
            if len(path_str) > 2 and path_str[0] == "/" and path_str[2] == ":":
                path_str = path_str[1:]
            return Path(path_str).as_uri()
        except Exception:
            return raw

    # Case 3: Raw local path (absolute or relative)
    try:
        p = Path(raw)
        if p.exists():
            return p.as_uri()
    except Exception:
        pass

    return ""


def open_url(target: str) -> Tuple[bool, str]:
    """Open a URL or local file path in the default browser.

    Returns (success: bool, human_message: str).
    """
    url = resolve_to_url(target)
    if not url:
        return False, f"Unsupported or invalid target: {target}"

    try:
        result = webbrowser.open(url)
        if result is False:
            return False, f"Browser refused to open: {url}"
        return True, f"Opened: {url}"
    except Exception as e:
        return False, f"Failed to open {url}: {e}"


def open_urls_batch(targets: List[str]) -> Tuple[List[str], List[str]]:
    """Open multiple URLs/paths. Returns (opened_messages, failed_messages)."""
    opened, failed = [], []
    for t in targets or []:
        ok, msg = open_url(t)
        (opened if ok else failed).append(msg)
    return opened, failed

APP_PATHS = {}

WEB_URLS = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chat.openai.com",
}

def open_any_app(apps_to_open, silent=False):
    opened = []
    failed = []

    if isinstance(apps_to_open, str):
        apps_to_open = [apps_to_open]

    for name in apps_to_open:
        name_lower = name.lower().strip()

        if name_lower in WEB_URLS:
            logger.info(f"Opening '{name}' in browser...")
            webbrowser.open(WEB_URLS[name_lower])
            opened.append(f"{name} (web)")
            continue

        logger.info(f"Attempting to open local app '{name}'...")
        try:
            open_app(name_lower, match_closest=True, throw_error=True)
            logger.info(f"Successfully opened: {name}")
            opened.append(name)

        except Exception as e:
            logger.warning(f"App '{name}' not found on system. Trying web fallback...")
            fallback_url = f"https://www.{name_lower.replace(' ', '')}.com"
            ok, msg = open_url(fallback_url)
            if ok:
                opened.append(f"{name} (web)")
                logger.info(f"Successfully opened via web fallback: {name}")
            else:
                logger.error(f"Failed to open {name} completely: {msg}")
                failed.append(name)

    if not silent and (opened or failed):
        try:
            success_names = [n for n in opened if " (web)" not in n]
            if success_names:
                logger.info(f"Sir, {', '.join(success_names)} khol diya.")
            if failed:
                logger.warning(f"Sir, {', '.join(failed)} nahi khul paaya.")
        except Exception:
            pass

    return opened

if __name__ == "__main__":
    apps_test = ["calculator", "youtube", "facebook"]
    opened_apps = open_any_app(apps_test)
    logger.info(f"Final Opened List: {opened_apps}")