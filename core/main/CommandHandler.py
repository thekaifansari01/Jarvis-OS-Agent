import time
import logging
from concurrent.futures import ThreadPoolExecutor
from core.brain.Processor.Processor import process_command
from core.brain.executor import execute_actions
from core.brain.Memory.Memory import ContextMemory
from core.voice import interrupt

_is_busy = False

def is_jarvis_busy() -> bool:
    global _is_busy
    return _is_busy

def main_command_processor(command: str, executor: ThreadPoolExecutor, memory: ContextMemory) -> None:
    global _is_busy
    _is_busy = True  
    
    try:
        raw = command.strip() if command else ""
        if not raw:
            return
        
        if interrupt.is_interrupted():
            interrupt.clear_interrupt()
            return
        
        result = process_command(raw, memory_instance=memory)
        execute_actions(result, executor)
        
        if 'response' not in result:
            result['response'] = "Action executed."
            
        metadata = result.get('metadata', {})
        if not metadata:
            apps_opened = result.get('apps_to_open', [])
            apps_closed = result.get('apps_to_close', [])
            sys_events = []

            if result.get('system_action'):
                sys_events.append(f"System Action: {result['system_action']}")
            if result.get('urls_to_open'):
                sys_events.append(f"Opened URLs: {', '.join(result['urls_to_open'])}")
            if result.get('workspace_file_to_open'):
                sys_events.append(f"Opened Workspace File: {result['workspace_file_to_open']}")

            if apps_opened or apps_closed or sys_events:
                metadata = {
                    "apps_opened": apps_opened,
                    "apps_closed": apps_closed,
                    "system_events": sys_events,
                    "files_touched": [] 
                }
              
        try:
            memory.add_message("USER", raw)
            memory.add_message("JARVIS", result.get('response', ''), metadata=metadata if metadata else None)
        except Exception as e:
            logging.error(f"Memory update failed: {e}")
            
        if result.get("response"):
            time.sleep(0.1)
            
    except Exception as e:
        logging.error(f"Command processor crash: {e}")
        
    finally:
        _is_busy = False  
        if memory and hasattr(memory, 'get_and_clear_feedback'):
            try:
                memory.get_and_clear_feedback()
            except Exception:
                pass