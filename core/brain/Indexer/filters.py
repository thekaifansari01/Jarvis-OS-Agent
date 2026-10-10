import os
import fnmatch
from pathlib import Path
from core.logger.logger import logger


DEFAULT_INCLUDE_EXTENSIONS = [
    ".txt", ".md", ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".csv",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".xml",
    ".html", ".css", ".scss", ".sass", ".less",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c",
    ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".sh", ".bash", ".ps1", ".bat", ".sql", ".r", ".m", ".lua"
]

DEFAULT_EXCLUDE_EXTENSIONS = [
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img", ".msi", ".cab",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
    ".db", ".sqlite", ".sqlite3", ".mdb", ".lock", ".log", ".tmp", ".bak",
    ".swp", ".sys", ".pyc", ".pyo", ".class", ".o", ".obj", ".pdb", ".ilk"
]

DEFAULT_EXCLUDE_FOLDERS = [
    "node_modules", "venv", ".venv", "env", "__pycache__",
    ".git", ".svn", ".hg", ".idea", ".vscode", ".vs",
    "build", "dist", "out", "target", "bin", "obj",
    ".next", ".nuxt", ".cache", "cache", "Cache",
    "coverage", ".pytest_cache", ".mypy_cache", ".tox",
    "temp", "tmp", "logs", "Logs", ".gradle", ".m2"
]

SYSTEM_PATHS_WINDOWS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information"
]

SENSITIVE_PATH_KEYWORDS = [
    ".ssh", ".aws", ".azure", ".gnupg", ".config/gcloud",
    ".env", ".git-credentials", ".netrc",
    "appdata", "wallet", "wallets", "keychain", "keychains",
    "cookies", "login data", "browser", "chrome/user data",
    "firefox/profiles", "edge/user data", "brave"
]

DEFAULT_FILTERS = {
    "include_extensions": DEFAULT_INCLUDE_EXTENSIONS,
    "exclude_extensions": DEFAULT_EXCLUDE_EXTENSIONS,
    "exclude_folders": DEFAULT_EXCLUDE_FOLDERS,
    "max_file_size_mb": 5,
    "min_file_size_bytes": 10,
    "max_depth": 15,
    "skip_hidden": True,
    "skip_symlinks": True,
    "custom_ignore_patterns": [],
    "sensitive_warn": True
}


class FilterEngine:
    def __init__(self, filters_dict=None):
        self._apply_defaults()
        if filters_dict:
            self.reload(filters_dict)

    def _apply_defaults(self):
        self.include_extensions = set(DEFAULT_INCLUDE_EXTENSIONS)
        self.exclude_extensions = set(DEFAULT_EXCLUDE_EXTENSIONS)
        self.exclude_folders = set(f.lower() for f in DEFAULT_EXCLUDE_FOLDERS)
        self.max_file_size_mb = 5
        self.max_file_size_bytes = 5 * 1024 * 1024
        self.min_file_size_bytes = 10
        self.max_depth = 15
        self.skip_hidden = True
        self.skip_symlinks = True
        self.custom_ignore_patterns = []
        self.sensitive_warn = True

    def reload(self, filters_dict):
        try:
            if not isinstance(filters_dict, dict):
                return

            if "include_extensions" in filters_dict:
                inc = filters_dict["include_extensions"]
                if isinstance(inc, list) and inc:
                    self.include_extensions = set(
                        e.lower() if e.startswith(".") else f".{e.lower()}" for e in inc
                    )

            if "exclude_extensions" in filters_dict:
                exc = filters_dict["exclude_extensions"]
                if isinstance(exc, list):
                    self.exclude_extensions = set(
                        e.lower() if e.startswith(".") else f".{e.lower()}" for e in exc
                    )

            if "exclude_folders" in filters_dict:
                ef = filters_dict["exclude_folders"]
                if isinstance(ef, list):
                    self.exclude_folders = set(f.lower() for f in ef)

            if "max_file_size_mb" in filters_dict:
                try:
                    self.max_file_size_mb = max(1, int(filters_dict["max_file_size_mb"]))
                    self.max_file_size_bytes = self.max_file_size_mb * 1024 * 1024
                except (ValueError, TypeError):
                    pass

            if "min_file_size_bytes" in filters_dict:
                try:
                    self.min_file_size_bytes = max(0, int(filters_dict["min_file_size_bytes"]))
                except (ValueError, TypeError):
                    pass

            if "max_depth" in filters_dict:
                try:
                    self.max_depth = max(1, int(filters_dict["max_depth"]))
                except (ValueError, TypeError):
                    pass

            if "skip_hidden" in filters_dict:
                self.skip_hidden = bool(filters_dict["skip_hidden"])

            if "skip_symlinks" in filters_dict:
                self.skip_symlinks = bool(filters_dict["skip_symlinks"])

            if "custom_ignore_patterns" in filters_dict:
                cp = filters_dict["custom_ignore_patterns"]
                if isinstance(cp, list):
                    self.custom_ignore_patterns = [str(p) for p in cp]

            if "sensitive_warn" in filters_dict:
                self.sensitive_warn = bool(filters_dict["sensitive_warn"])

            logger.info("FilterEngine reloaded with updated rules.")
        except Exception as e:
            logger.error(f"FilterEngine reload failed: {e}")

    def should_index(self, file_path):
        try:
            path = Path(file_path)
        except Exception:
            return False

        try:
            name = path.name
            ext = path.suffix.lower()

            if self.skip_hidden and name.startswith("."):
                return False

            if ext in self.exclude_extensions:
                return False

            if ext not in self.include_extensions:
                return False

            for pattern in self.custom_ignore_patterns:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    return False

            try:
                stat = path.stat()
            except (OSError, PermissionError):
                return False

            if stat.st_size < self.min_file_size_bytes:
                return False

            if stat.st_size > self.max_file_size_bytes:
                return False

            if self._is_binary(path):
                return False

            return True

        except Exception as e:
            logger.warning(f"FilterEngine should_index error for {file_path}: {e}")
            return False

    def should_skip_folder(self, folder_name):
        try:
            if not folder_name:
                return True
            if self.skip_hidden and folder_name.startswith("."):
                return True
            if folder_name.lower() in self.exclude_folders:
                return True
            for pattern in self.custom_ignore_patterns:
                if fnmatch.fnmatch(folder_name.lower(), pattern.lower()):
                    return True
            return False
        except Exception:
            return True

    def is_system_path(self, path):
        try:
            resolved = str(Path(path).resolve()).lower()
            for sys_path in SYSTEM_PATHS_WINDOWS:
                if resolved.startswith(sys_path.lower()):
                    return True
            if os.name != "nt":
                unix_system = ["/etc", "/usr", "/bin", "/sbin", "/var", "/sys", "/proc"]
                for up in unix_system:
                    if resolved.startswith(up):
                        return True
            return False
        except Exception:
            return True

    def is_sensitive_path(self, path):
        try:
            resolved = str(Path(path).resolve()).lower()
            for keyword in SENSITIVE_PATH_KEYWORDS:
                if keyword.lower() in resolved:
                    return True
            return False
        except Exception:
            return False

    def _is_binary(self, file_path):
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                if not chunk:
                    return False
                if b"\x00" in chunk:
                    return True
                return False
        except Exception:
            return True

    def get_defaults(self):
        return dict(DEFAULT_FILTERS)

    def export_config(self):
        return {
            "include_extensions": sorted(self.include_extensions),
            "exclude_extensions": sorted(self.exclude_extensions),
            "exclude_folders": sorted(self.exclude_folders),
            "max_file_size_mb": self.max_file_size_mb,
            "min_file_size_bytes": self.min_file_size_bytes,
            "max_depth": self.max_depth,
            "skip_hidden": self.skip_hidden,
            "skip_symlinks": self.skip_symlinks,
            "custom_ignore_patterns": list(self.custom_ignore_patterns),
            "sensitive_warn": self.sensitive_warn
        }