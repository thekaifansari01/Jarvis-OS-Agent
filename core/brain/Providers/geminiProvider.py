import os
from typing import List, Dict, Any, Optional, Generator

from google import genai
from google.genai import types

from core.brain.Providers.baseProvider import BaseLLMProvider
from core.brain.config import GEMINI_API_KEY, GEMINI_AGENT_MODEL
from core.logger.logger import logger

class GeminiProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str = None,
        model: str = None
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_AGENT_MODEL
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in config")
        
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"✅ GeminiProvider initialized with model: {self.model}")
    
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
            # Convert messages to Gemini Content format
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            
            # Build config
            config_kwargs = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if tools:
                config_kwargs["tools"] = tools  # tools are already in Gemini format from Prompts.py
            if tool_choice == "auto":
                config_kwargs["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))
            
            config = types.GenerateContentConfig(**config_kwargs)
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            # Parse response
            content_text = ""
            tool_calls = []
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        content_text += part.text
                    elif part.function_call:
                        tool_calls.append({
                            "function": {
                                "name": part.function_call.name,
                                "arguments": dict(part.function_call.args) if part.function_call.args else {}
                            }
                        })
            
            return {
                "content": content_text,
                "tool_calls": tool_calls,
                "provider": "gemini",
                "error": None
            }
            
        except Exception as e:
            logger.error(f"❌ GeminiProvider error: {e}")
            return {
                "content": "",
                "tool_calls": [],
                "provider": "gemini",
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
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )
            
            config_kwargs = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if tools:
                config_kwargs["tools"] = tools
            if tool_choice == "auto":
                config_kwargs["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))
            
            config = types.GenerateContentConfig(**config_kwargs)
            
            response = self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config
            )
            
            for chunk in response:
                if chunk.candidates and chunk.candidates[0].content.parts:
                    for part in chunk.candidates[0].content.parts:
                        if part.text:
                            yield {
                                "content": part.text,
                                "tool_calls": [],
                                "provider": "gemini",
                                "error": None
                            }
                        elif part.function_call:
                            yield {
                                "content": "",
                                "tool_calls": [{
                                    "function": {
                                        "name": part.function_call.name,
                                        "arguments": dict(part.function_call.args) if part.function_call.args else {}
                                    }
                                }],
                                "provider": "gemini",
                                "error": None
                            }
                            
        except Exception as e:
            logger.error(f"❌ GeminiProvider stream error: {e}")
            yield {
                "content": "",
                "tool_calls": [],
                "provider": "gemini",
                "error": str(e)
            }