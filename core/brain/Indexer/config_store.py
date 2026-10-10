import json
import os
import threading
from pathlib import Path
from datetime import datetime
from core.logger.logger import logger
from core.brain.Indexer.filters import DEFAULT_FILTERS


DEFAULT_SETTINGS = {
    "dashboard_port": 8080,
    "auto_index_on_startup": True,
    "indexer_enabled": True,
    "log_level": "INFO"
}


class ConfigStore:
    def __init__(self, base_dir="Data/jarvis_indexer"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.folders_file = self.base_dir / "folders.json"
        self.filters_file = self.base_dir / "filters.json"
        self.settings_file = self.base_dir / "settings.json"

        self._lock = threading.RLock()
        self._ensure_defaults()

    def _ensure_defaults(self):
        with self._lock:
            if not self.folders_file.exists():
                self._write_json(self.folders_file, [])
                logger.info(f"ConfigStore: created default {self.folders_file.name}")

            if not self.filters_file.exists():
                self._write_json(self.filters_file, DEFAULT_FILTERS)
                logger.info(f"ConfigStore: created default {self.filters_file.name}")

            if not self.settings_file.exists():
                self._write_json(self.settings_file, DEFAULT_SETTINGS)
                logger.info(f"ConfigStore: created default {self.settings_file.name}")

    def _read_json(self, file_path, default):
        try:
            with self._lock:
                if not file_path.exists():
                    return default
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data is None:
                        return default
                    return data
        except json.JSONDecodeError as e:
            logger.error(f"ConfigStore: JSON decode failed for {file_path.name}: {e}")
            return default
        except Exception as e:
            logger.error(f"ConfigStore: read failed for {file_path.name}: {e}")
            return default

    def _write_json(self, file_path, data):
        try:
            with self._lock:
                tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, file_path)
        except Exception as e:
            logger.error(f"ConfigStore: write failed for {file_path.name}: {e}")

    def load_folders(self):
        data = self._read_json(self.folders_file, [])
        if not isinstance(data, list):
            logger.warning("ConfigStore: folders.json malformed, resetting to empty list.")
            return []
        valid = []
        for item in data:
            if isinstance(item, dict) and item.get("path"):
                valid.append({
                    "path": item["path"],
                    "added_at": item.get("added_at", datetime.now().isoformat()),
                    "last_indexed": item.get("last_indexed", ""),
                    "is_default": bool(item.get("is_default", False)),
                    "enabled": bool(item.get("enabled", True))
                })
        return valid

    def save_folders(self, folders):
        if not isinstance(folders, list):
            logger.error("ConfigStore: save_folders called with non-list.")
            return False
        try:
            self._write_json(self.folders_file, folders)
            return True
        except Exception as e:
            logger.error(f"ConfigStore: save_folders failed: {e}")
            return False

    def load_filters(self):
        data = self._read_json(self.filters_file, DEFAULT_FILTERS)
        if not isinstance(data, dict):
            logger.warning("ConfigStore: filters.json malformed, using defaults.")
            return dict(DEFAULT_FILTERS)
        merged = dict(DEFAULT_FILTERS)
        merged.update(data)
        return merged

    def save_filters(self, filters_dict):
        if not isinstance(filters_dict, dict):
            logger.error("ConfigStore: save_filters called with non-dict.")
            return False
        try:
            self._write_json(self.filters_file, filters_dict)
            return True
        except Exception as e:
            logger.error(f"ConfigStore: save_filters failed: {e}")
            return False

    def load_settings(self):
        data = self._read_json(self.settings_file, DEFAULT_SETTINGS)
        if not isinstance(data, dict):
            logger.warning("ConfigStore: settings.json malformed, using defaults.")
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged

    def save_settings(self, settings_dict):
        if not isinstance(settings_dict, dict):
            logger.error("ConfigStore: save_settings called with non-dict.")
            return False
        try:
            self._write_json(self.settings_file, settings_dict)
            return True
        except Exception as e:
            logger.error(f"ConfigStore: save_settings failed: {e}")
            return False

    def reset_filters(self):
        try:
            self._write_json(self.filters_file, DEFAULT_FILTERS)
            logger.info("ConfigStore: filters reset to defaults.")
            return True
        except Exception as e:
            logger.error(f"ConfigStore: reset_filters failed: {e}")
            return False

    def get_paths(self):
        return {
            "base_dir": str(self.base_dir),
            "folders_file": str(self.folders_file),
            "filters_file": str(self.filters_file),
            "settings_file": str(self.settings_file)
        }


config_store = ConfigStore()