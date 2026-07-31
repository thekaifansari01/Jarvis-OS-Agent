import os
import json
import requests
from typing import List, Dict, Any, Optional, Generator

from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.config import (
    REGOLO_API_KEY, 
    REGOLO_BASE_URL, 
    REGOLO_MODEL, 
    REGOLO_THINKING_ENABLED
)
from core.logger.logger import logger

class RegoloProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        thinking_enabled: bool = None
    ):
        self.api_key = api_key or REGOLO_API_KEY
        self.base_url = (base_url or REGOLO_BASE_URL).rstrip('/')
        self.model = model or REGOLO_MODEL
        self.thinking_enabled = thinking_enabled if thinking_enabled is not None else REGOLO_THINKING_ENABLED
        
        if not self.api_key:
            raise ValueError("REGOLO_API_KEY not found in config")
        
        self._converted_tools_cache = None
        logger.info(f"✅ RegoloProvider initialized with model: {self.model}")
    
    def _convert_tools_to_openai(self, tools_list: List[Any]) -> List[Dict[str, Any]]:
        if not tools_list:
            return []
        
        if self._converted_tools_cache is not None:
            return self._converted_tools_cache
        
        openai_tools = []
        
        try:
            for tool_wrapper in tools_list:
                if hasattr(tool_wrapper, 'function_declarations'):
                    for func in tool_wrapper.function_declarations:
                        params = func.parameters
                        
                        openai_params = {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                        
                        if params:
                            if hasattr(params, 'properties') and params.properties:
                                for prop_name, prop_schema in params.properties.items():
                                    prop_type = "string"
                                    if hasattr(prop_schema, 'type'):
                                        type_str = str(prop_schema.type).upper()
                                        if "STRING" in type_str:
                                            prop_type = "string"
                                        elif "INTEGER" in type_str:
                                            prop_type = "integer"
                                        elif "NUMBER" in type_str:
                                            prop_type = "number"
                                        elif "BOOLEAN" in type_str:
                                            prop_type = "boolean"
                                        elif "ARRAY" in type_str:
                                            prop_type = "array"
                                        elif "OBJECT" in type_str:
                                            prop_type = "object"
                                    
                                    prop_obj = {"type": prop_type}
                                    
                                    if hasattr(prop_schema, 'description') and prop_schema.description:
                                        prop_obj["description"] = prop_schema.description
                                    
                                    if prop_type == "array" and hasattr(prop_schema, 'items') and prop_schema.items:
                                        items_type = "string"
                                        if hasattr(prop_schema.items, 'type'):
                                            items_type_str = str(prop_schema.items.type).upper()
                                            if "STRING" in items_type_str:
                                                items_type = "string"
                                            elif "INTEGER" in items_type_str:
                                                items_type = "integer"
                                        prop_obj["items"] = {"type": items_type}
                                    
                                    openai_params["properties"][prop_name] = prop_obj
                            
                            if hasattr(params, 'required') and params.required:
                                openai_params["required"] = list(params.required)
                        
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": func.name,
                                "description": func.description or "",
                                "parameters": openai_params
                            }
                        })
            
            self._converted_tools_cache = openai_tools
            return openai_tools
            
        except Exception as e:
            logger.error(f"❌ Error converting tools for Regolo: {e}")
            return []
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Any]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            openai_tools = self._convert_tools_to_openai(tools) if tools else []
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
                "reasoning": {
                    "enabled": self.thinking_enabled,
                    "max_tokens": 2048
                }
            }
            
            if openai_tools:
                payload["tools"] = openai_tools
                payload["tool_choice"] = tool_choice
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data["choices"][0]["message"]
                
                content = message.get("content") or ""
                reasoning_content = message.get("reasoning_content") or message.get("reasoning") or ""
                tool_calls = message.get("tool_calls", [])
                
                formatted_tool_calls = []
                for tc in tool_calls:
                    formatted_tool_calls.append({
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                        }
                    })
                
                return {
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "tool_calls": formatted_tool_calls,
                    "provider": "regolo",
                    "error": None
                }
            else:
                error_text = response.text
                logger.error(f"❌ Regolo API Error: {response.status_code} - {error_text}")
                return {
                    "content": "",
                    "reasoning_content": "",
                    "tool_calls": [],
                    "provider": "regolo",
                    "error": f"HTTP {response.status_code}: {error_text}"
                }
                
        except Exception as e:
            logger.error(f"❌ RegoloProvider error: {e}")
            return {
                "content": "",
                "reasoning_content": "",
                "tool_calls": [],
                "provider": "regolo",
                "error": str(e)
            }
    
    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Any]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[Dict[str, Any], None, None]:
        try:
            openai_tools = self._convert_tools_to_openai(tools) if tools else []
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                "reasoning": {
                    "enabled": self.thinking_enabled,
                    "max_tokens": 2048
                }
            }
            
            if openai_tools:
                payload["tools"] = openai_tools
                payload["tool_choice"] = tool_choice
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=120
            )
            
            accumulated_tool_calls = {}

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data = line[6:]
                            if data != '[DONE]':
                                try:
                                    chunk = json.loads(data)
                                    if chunk.get('choices'):
                                        delta = chunk['choices'][0].get('delta', {})
                                        
                                        rc = delta.get('reasoning_content') or delta.get('reasoning')
                                        if rc:
                                            yield {
                                                "content": "",
                                                "reasoning_content": rc,
                                                "tool_calls": [],
                                                "provider": "regolo",
                                                "error": None
                                            }
                                        
                                        if delta.get('content'):
                                            yield {
                                                "content": delta['content'],
                                                "reasoning_content": "",
                                                "tool_calls": [],
                                                "provider": "regolo",
                                                "error": None
                                            }
                                        
                                        if delta.get('tool_calls'):
                                            for tc in delta['tool_calls']:
                                                idx = tc.get('index', 0)
                                                if idx not in accumulated_tool_calls:
                                                    accumulated_tool_calls[idx] = {"name": "", "arguments": ""}
                                                fn = tc.get('function', {})
                                                if fn.get('name'):
                                                    accumulated_tool_calls[idx]["name"] += fn['name']
                                                if fn.get('arguments'):
                                                    accumulated_tool_calls[idx]["arguments"] += fn['arguments']
                                                
                                except json.JSONDecodeError:
                                    pass
                
                if accumulated_tool_calls:
                    formatted_tool_calls = []
                    for idx in sorted(accumulated_tool_calls.keys()):
                        tc_data = accumulated_tool_calls[idx]
                        raw_args = tc_data["arguments"]
                        try:
                            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else raw_args
                        except Exception:
                            parsed_args = {}
                        formatted_tool_calls.append({
                            "function": {
                                "name": tc_data["name"],
                                "arguments": parsed_args
                            }
                        })
                    yield {
                        "content": "",
                        "reasoning_content": "",
                        "tool_calls": formatted_tool_calls,
                        "provider": "regolo",
                        "error": None
                    }
            else:
                yield {
                    "content": "",
                    "reasoning_content": "",
                    "tool_calls": [],
                    "provider": "regolo",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            logger.error(f"❌ RegoloProvider stream error: {e}")
            yield {
                "content": "",
                "reasoning_content": "",
                "tool_calls": [],
                "provider": "regolo",
                "error": str(e)
            }