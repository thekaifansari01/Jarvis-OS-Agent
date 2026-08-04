import os
import py_compile

class JarvisFileEditor:
    def __init__(self, workspace_dir=None):
        self.workspace = workspace_dir or os.getcwd()
        self.MAX_FILE_SIZE = 1024 * 1024
        self.MAX_CREATE_MANY_FILES = 10
        self.MAX_REPO_MAP_DEPTH = 4
        self.MAX_REPO_MAP_FILES = 50
        self.MAX_VIEW_CHARS = 15000

    def _validate_syntax(self, file_path):
        if not file_path.endswith(".py"):
            return ""
        try:
            py_compile.compile(file_path, doraise=True)
            return " [Syntax Check: OK]"
        except py_compile.PyCompileError as e:
            return f"\n[CRITICAL SYNTAX ERROR DETECTED AFTER EDIT]:\n{e.msg}"
        except Exception as e:
            return f"\n[LINTER WARNING]: {str(e)}"

    def _normalize_block(self, block):
        if not block:
            return block
        lines = block.split('\n')
        lines = [line.rstrip() for line in lines]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return '\n'.join(lines)

    def _truncate_text(self, text, max_chars, label="Content"):
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return (f"{text[:half]}\n[... TRUNCATED: {len(text) - max_chars} chars ...]\n{text[-half:]}")

    def get_repo_map(self, file_path=None, max_files=50, max_depth=4):
        try:
            target_path = file_path if file_path else self.workspace
            if not os.path.exists(target_path):
                return f"[ERROR] Path '{target_path}' does not exist. Please provide a valid absolute path."
            tree_lines = [f"Project Architecture (Root: {target_path}):"]
            tree_lines.append(f"Max Depth: {max_depth}, Max Files: {max_files}")
            tree_lines.append("")
            count = 0
            skipped_dirs = [".venv", "node_modules", "__pycache__", ".git", "Data", "venv", "env", ".idea", ".vscode", "dist", "build", "target"]
            skip_extensions = [".pyc", ".pyo", ".so", ".dll", ".exe", ".class", ".jar", ".war", ".ear", ".log", ".tmp", ".cache", ".DS_Store"]
            include_extensions = [".py", ".json", ".md", ".txt", ".html", ".js", ".css", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh", ".bat", ".ps1", ".xml", ".svg"]
            for root, dirs, files in os.walk(target_path):
                rel_path = os.path.relpath(root, target_path)
                depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                if depth > max_depth:
                    dirs.clear()
                    continue
                dirs[:] = [d for d in dirs if d not in skipped_dirs]
                for file in files:
                    try:
                        file_path_full = os.path.join(root, file)
                        if os.path.getsize(file_path_full) > self.MAX_FILE_SIZE:
                            continue
                    except:
                        pass
                    ext = os.path.splitext(file)[1].lower()
                    if ext in skip_extensions:
                        continue
                    if not any(file.endswith(ext) for ext in include_extensions):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, file), target_path)
                    clean_path = rel_path.replace("\\", "/")
                    tree_lines.append(f"  - {clean_path}")
                    count += 1
                    if count >= max_files:
                        tree_lines.append("  ... (truncated remaining files)")
                        return "\n".join(tree_lines)
            tree_lines.append("")
            tree_lines.append(f"[SUCCESS] Found {count} files.")
            return "\n".join(tree_lines)
        except Exception as e:
            return f"[ERROR] Could not generate repo map: {e}"

    def replace_block(self, file_path, search_block, replace_block):
        try:
            norm_search = self._normalize_block(search_block)
            norm_replace = self._normalize_block(replace_block)
            if not norm_search:
                return "[ERROR] Search block cannot be empty."
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            norm_content = content.replace("\r\n", "\n")
            matches = norm_content.count(norm_search)
            if matches == 0:
                alt_search = norm_search.rstrip('\n')
                if alt_search and norm_content.count(alt_search) > 0:
                    matches = norm_content.count(alt_search)
                    norm_search = alt_search
                else:
                    if norm_search != search_block:
                        matches = norm_content.count(search_block)
                        if matches > 0:
                            norm_search = search_block
                        else:
                            return f"[ERROR] Search block not found in '{file_path}'. Ensure indentation and spacing match exactly."
            if matches == 0:
                return f"[ERROR] Search block not found in '{file_path}'. Ensure indentation and spacing match exactly."
            elif matches > 1:
                return f"[ERROR] Search block found {matches} times in '{file_path}'. Please provide a larger, more unique search block."
            new_content = norm_content.replace(norm_search, norm_replace)
            with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
            syntax_status = self._validate_syntax(file_path)
            if "CRITICAL SYNTAX ERROR" in syntax_status:
                return f"[ERROR] Block replaced in '{file_path}', but broke code syntax!{syntax_status}"
            return f"[SUCCESS] Block replaced cleanly in '{file_path}'.{syntax_status}"
        except Exception as e:
            return f"[ERROR] Failed to replace block in '{file_path}': {e}"

    def view(self, file_path=None, file_paths=None, start_line=None, end_line=None):
        try:
            if not file_path and not file_paths:
                return "[ERROR] Either 'file_path' or 'file_paths' must be provided."
            if file_paths and not isinstance(file_paths, list):
                return "[ERROR] 'file_paths' must be a list of file paths."
            if file_path and file_paths:
                return "[ERROR] Provide either 'file_path' (single) or 'file_paths' (list), not both."

            if file_paths:
                results = []
                for fp in file_paths:
                    res = self.view(fp, start_line=start_line, end_line=end_line)
                    results.append(f"=== {fp} ===\n{res}")
                combined = "\n\n".join(results)
                truncated = self._truncate_text(combined, self.MAX_VIEW_CHARS, "Combined output")
                return f"[SUCCESS] Batch view of {len(file_paths)} files:\n\n{truncated}"

            try:
                file_size = os.path.getsize(file_path)
                if file_size > self.MAX_FILE_SIZE and (start_line is None and end_line is None):
                    return f"[WARNING] File '{file_path}' is {file_size} bytes (max {self.MAX_FILE_SIZE}). Use line range to view partial content."
            except:
                pass

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            total_lines = len(lines)

            if start_line and end_line:
                start = max(1, min(start_line, total_lines))
                end = min(end_line, total_lines)
                if start > end:
                    start, end = end, start
                content = "".join(lines[start-1:end])
                return f"[SUCCESS] Viewed lines {start}-{end} of '{file_path}' ({total_lines} lines total):\n\n{content}"
            elif start_line:
                start = max(1, min(start_line, total_lines))
                content = "".join(lines[start-1:start+9])
                return f"[SUCCESS] Viewed 10 lines starting from line {start}:\n\n{content}"
            elif end_line:
                end = min(end_line, total_lines)
                start = max(1, end - 9)
                content = "".join(lines[start-1:end])
                return f"[SUCCESS] Viewed 10 lines ending at line {end}:\n\n{content}"

            full_content = "".join(lines)
            if len(full_content) > self.MAX_VIEW_CHARS:
                truncated_content = self._truncate_text(full_content, self.MAX_VIEW_CHARS, f"File '{file_path}'")
                return f"[SUCCESS] Viewed entire file '{file_path}' ({total_lines} lines, {len(full_content)} chars) - TRUNCATED to {self.MAX_VIEW_CHARS} chars:\n\n{truncated_content}"
            else:
                return f"[SUCCESS] Viewed entire file '{file_path}' ({total_lines} lines):\n\n{full_content}"
        except Exception as e:
            return f"[ERROR] Failed to view '{file_path}': {e}"

    def create(self, file_path=None, content="", files=None):
        try:
            if file_path and files:
                return "[ERROR] Provide either 'file_path' (single) or 'files' (list), not both."
            if not file_path and not files:
                return "[ERROR] Either 'file_path' or 'files' must be provided."

            if files:
                if not isinstance(files, list) or not files:
                    return "[ERROR] 'files' must be a non-empty list of objects with 'file_path' and 'content'."
                if len(files) > self.MAX_CREATE_MANY_FILES:
                    return f"[ERROR] Too many files ({len(files)}). Max allowed: {self.MAX_CREATE_MANY_FILES}."
                results = []
                for item in files:
                    fp = item.get("file_path")
                    cont = item.get("content", "")
                    if not fp:
                        results.append("[ERROR] Skipped entry: missing 'file_path'.")
                        continue
                    res = self.create(file_path=fp, content=cont)
                    results.append(res)
                return "\n".join(results)

            dir_name = os.path.dirname(os.path.abspath(file_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            if len(content) > 10 * 1024 * 1024:
                return f"[ERROR] File content too large ({len(content)} bytes). Max allowed 10MB."
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            syntax_status = self._validate_syntax(file_path)
            if "CRITICAL SYNTAX ERROR" in syntax_status:
                return f"[ERROR] Created file '{file_path}', but syntax is invalid!{syntax_status}"
            return f"[SUCCESS] Created file '{file_path}' successfully ({len(content)} chars).{syntax_status}"
        except Exception as e:
            return f"[ERROR] Failed to create file '{file_path}': {e}"