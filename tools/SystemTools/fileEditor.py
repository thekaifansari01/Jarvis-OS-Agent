import os
import py_compile
import traceback
from datetime import datetime

class JarvisFileEditor:
    def __init__(self, workspace_dir=None):
        self.workspace = workspace_dir or os.getcwd()
        self.MAX_FILE_SIZE = 1024 * 1024 
        self.MAX_CREATE_MANY_FILES = 10
        self.MAX_REPO_MAP_DEPTH = 4
        self.MAX_REPO_MAP_FILES = 50

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
        """Normalize block for matching - strip trailing spaces, normalize indentation"""
        if not block:
            return block
        lines = block.split('\n')
        lines = [line.rstrip() for line in lines]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return '\n'.join(lines)

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
            
            with open(file_path, "r", encoding="utf-8") as f:
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

    def view(self, file_path, start_line=None, end_line=None):
        try:
            try:
                file_size = os.path.getsize(file_path)
                if file_size > self.MAX_FILE_SIZE and (start_line is None or end_line is None):
                    return f"[WARNING] File '{file_path}' is {file_size} bytes (max {self.MAX_FILE_SIZE}). Use line range to view partial content."
            except:
                pass
            
            with open(file_path, "r", encoding="utf-8") as f:
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
            
            content = "".join(lines[:500])  
            if total_lines > 500:
                content += f"\n[... TRUNCATED: {total_lines - 500} more lines ...]"
            
            return f"[SUCCESS] Viewed entire file '{file_path}' ({total_lines} lines total):\n\n{content}"
        except Exception as e:
            return f"[ERROR] Failed to view '{file_path}': {e}"

    def create(self, file_path, content=""):
        try:
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

    def create_many(self, files):
        if not isinstance(files, list) or not files:
            return "[ERROR] 'files' must be a non-empty list of dictionaries with 'file_path' and 'content'."
        
        if len(files) > self.MAX_CREATE_MANY_FILES:
            return f"[ERROR] Too many files ({len(files)}). Max allowed: {self.MAX_CREATE_MANY_FILES}."
        
        results = []
        for item in files:
            file_path = item.get("file_path")
            content = item.get("content", "")
            if not file_path:
                results.append("[ERROR] Skipped entry: missing 'file_path'.")
                continue
            res = self.create(file_path, content)
            results.append(res)
        
        return "\n".join(results)