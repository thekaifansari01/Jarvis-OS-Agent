import os
import py_compile
import traceback
from datetime import datetime

class JarvisFileEditor:
    def __init__(self, workspace_dir=None):
        self.workspace = workspace_dir or os.getcwd()

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

    def get_repo_map(self, max_files=30):
        try:
            tree_lines = [f"Project Architecture (Root: {self.workspace}):"]
            count = 0
            for root, dirs, files in os.walk(self.workspace):
                dirs[:] = [d for d in dirs if d not in [".venv", "node_modules", "__pycache__", ".git", "Data"]]
                for file in files:
                    if file.endswith((".py", ".json", ".md", ".txt", ".html", ".js", ".css")):
                        rel_path = os.path.relpath(os.path.join(root, file), self.workspace)
                        clean_path = rel_path.replace("\\", "/")
                        tree_lines.append(f"  - {clean_path}")
                        count += 1
                        if count >= max_files:
                            tree_lines.append("  ... (truncated remaining files)")
                            return "\n".join(tree_lines)
            return "\n".join(tree_lines)
        except Exception as e:
            return f"[ERROR] Could not generate repo map: {e}"

    def replace_block(self, file_path, search_block, replace_block):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            norm_content = content.replace("\r\n", "\n")
            norm_search = search_block.replace("\r\n", "\n")
            norm_replace = replace_block.replace("\r\n", "\n")

            matches = norm_content.count(norm_search)
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
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if start_line and end_line:
                content = "".join(lines[start_line-1:end_line])
                return f"[SUCCESS] Viewed lines {start_line}-{end_line} of '{file_path}':\n\n{content}"
            content = "".join(lines)
            return f"[SUCCESS] Viewed entire file '{file_path}' ({len(lines)} lines total):\n\n{content}"
        except Exception as e:
            return f"[ERROR] Failed to view '{file_path}': {e}"

    def create(self, file_path, content=""):
        try:
            dir_name = os.path.dirname(os.path.abspath(file_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
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