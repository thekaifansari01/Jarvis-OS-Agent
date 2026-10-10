import os
from pathlib import Path
from core.logger.logger import logger


WINDOWS_LEGACY_JUNCTIONS = {
    "my music",
    "my pictures",
    "my videos",
    "my documents"
}

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class FileWalker:
    def __init__(self, filter_engine):
        self.filter_engine = filter_engine
        self._skipped_counts = {
            "permission_denied": 0,
            "symlink": 0,
            "hidden": 0,
            "excluded_folder": 0,
            "depth_exceeded": 0,
            "legacy_junction": 0,
            "other_errors": 0
        }

    def walk_folder(self, folder_path):
        self._reset_counters()
        try:
            root = Path(folder_path).resolve()
        except Exception as e:
            logger.error(f"FileWalker: path resolve failed for {folder_path}: {e}")
            return

        if not root.exists():
            logger.warning(f"FileWalker: folder does not exist: {root}")
            return

        if not root.is_dir():
            logger.warning(f"FileWalker: not a directory: {root}")
            return

        logger.info(f"FileWalker: scanning started: {root}")
        yield from self._walk_recursive(root, 0)
        logger.info(
            f"FileWalker: scan complete for {root} | "
            f"permission_denied={self._skipped_counts['permission_denied']} | "
            f"symlinks={self._skipped_counts['symlink']} | "
            f"hidden={self._skipped_counts['hidden']} | "
            f"excluded_folders={self._skipped_counts['excluded_folder']} | "
            f"legacy_junctions={self._skipped_counts['legacy_junction']} | "
            f"depth_exceeded={self._skipped_counts['depth_exceeded']}"
        )

    def _walk_recursive(self, folder, depth):
        if depth > self.filter_engine.max_depth:
            self._skipped_counts["depth_exceeded"] += 1
            logger.warning(f"FileWalker: max depth reached at {folder}")
            return

        if self._is_legacy_junction(folder):
            self._skipped_counts["legacy_junction"] += 1
            return

        try:
            entries = list(os.scandir(folder))
        except PermissionError:
            self._skipped_counts["permission_denied"] += 1
            logger.warning(f"FileWalker: permission denied: {folder}")
            return
        except OSError as e:
            self._skipped_counts["other_errors"] += 1
            logger.warning(f"FileWalker: os error at {folder}: {e}")
            return

        for entry in entries:
            try:
                if self._is_symlink(entry):
                    if self.filter_engine.skip_symlinks:
                        self._skipped_counts["symlink"] += 1
                        continue

                if entry.is_dir(follow_symlinks=False):
                    if self._should_skip_dir(entry.name):
                        continue
                    yield from self._walk_recursive(Path(entry.path), depth + 1)

                elif entry.is_file(follow_symlinks=False):
                    file_path = Path(entry.path)
                    if self.filter_engine.should_index(file_path):
                        yield file_path

            except PermissionError:
                self._skipped_counts["permission_denied"] += 1
                continue
            except OSError as e:
                self._skipped_counts["other_errors"] += 1
                logger.warning(f"FileWalker: entry error at {entry.path}: {e}")
                continue
            except Exception as e:
                self._skipped_counts["other_errors"] += 1
                logger.warning(f"FileWalker: unexpected entry error at {entry.path}: {e}")
                continue

    def _is_symlink(self, entry):
        try:
            return entry.is_symlink()
        except Exception:
            return False

    def _should_skip_dir(self, dir_name):
        if not dir_name:
            return True

        if self.filter_engine.skip_hidden and dir_name.startswith("."):
            self._skipped_counts["hidden"] += 1
            return True

        if self.filter_engine.should_skip_folder(dir_name):
            self._skipped_counts["excluded_folder"] += 1
            return True

        return False

    def _is_legacy_junction(self, folder):
        if os.name != "nt":
            return False
        try:
            name = Path(folder).name.lower()
            if name in WINDOWS_LEGACY_JUNCTIONS:
                return True
            stat_result = os.stat(folder, follow_symlinks=False)
            attrs = getattr(stat_result, "st_file_attributes", 0)
            if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
                return True
            return False
        except Exception:
            return False

    def _reset_counters(self):
        for key in self._skipped_counts:
            self._skipped_counts[key] = 0

    def get_last_scan_stats(self):
        return dict(self._skipped_counts)

    def count_files(self, folder_path):
        total = 0
        for _ in self.walk_folder(folder_path):
            total += 1
        return total