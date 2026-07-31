import os
from datetime import datetime

class JarvisFileEditor:
    def __init__(self, workspace_dir=None):
        self.workspace = workspace_dir or os.getcwd()
    
    def view(self, file_path, start_line=None, end_line=None):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if start_line and end_line:
                content = ''.join(lines[start_line-1:end_line])
                return f"[SUCCESS] Viewed lines {start_line}-{end_line} of '{file_path}':\n\n{content}"
            
            content = ''.join(lines)
            return f"[SUCCESS] Viewed entire file '{file_path}' ({len(lines)} lines total):\n\n{content}"
        except Exception as e:
            return f"[ERROR] Failed to view '{file_path}': {e}"
    
    def replace_string(self, file_path, old_str, new_str):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_str not in content:
                return f"[ERROR] String '{old_str}' not found in '{file_path}'. No changes made."
            
            new_content = content.replace(old_str, new_str)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"[SUCCESS] Replaced string '{old_str}' with '{new_str}' in '{file_path}'."
        except Exception as e:
            return f"[ERROR] Failed to replace string in '{file_path}': {e}"
    
    def replace_lines(self, file_path, start_line, end_line, new_content):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            new_lines = new_content.splitlines(keepends=True)
            if not new_lines:
                new_lines = ['\n']
            
            lines[start_line-1:end_line] = new_lines
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"[SUCCESS] Replaced lines {start_line} to {end_line} in '{file_path}' with new content."
        except Exception as e:
            return f"[ERROR] Failed to replace lines {start_line}-{end_line} in '{file_path}': {e}"
    
    def insert(self, file_path, line_number, text):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            lines.insert(line_number - 1, text + '\n')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"[SUCCESS] Inserted text at line {line_number} in '{file_path}'."
        except Exception as e:
            return f"[ERROR] Failed to insert text at line {line_number} in '{file_path}': {e}"
    
    def delete_lines(self, file_path, start_line, end_line):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            del lines[start_line-1:end_line]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"[SUCCESS] Deleted lines {start_line} to {end_line} from '{file_path}'."
        except Exception as e:
            return f"[ERROR] Failed to delete lines {start_line}-{end_line} in '{file_path}': {e}"
    
    def create(self, file_path, content=""):
        try:
            dir_name = os.path.dirname(os.path.abspath(file_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            char_count = len(content)
            return f"[SUCCESS] Created file '{file_path}' successfully with {char_count} characters. File is ready."
        except Exception as e:
            return f"[ERROR] Failed to create file '{file_path}': {e}"