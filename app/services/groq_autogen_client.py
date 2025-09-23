"""
Groq client for AutoGen multi-agent conversations.
Provides fast LLM inference for AutoGen agents using Groq API.
"""

import asyncio
import httpx
import json
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass

from app.services.groq_client import GroqClient
from app.config.logging import get_logger

logger = get_logger(__name__)


class GroqLLMClient:
    """
    AutoGen-compatible client that uses Groq API instead of OpenAI.
    Provides the same interface as OpenAI client but with Groq's speed.
    """
    
    def __init__(self, model: str = "llama-3.1-8b-instant"):
        self.groq_client = GroqClient()
        self.model = model
        
    async def create_response(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a response using Groq API, compatible with AutoGen interface.
        
        Args:
            messages: List of message dictionaries
            **kwargs: Additional parameters
            
        Returns:
            Response in OpenAI-compatible format
        """
        try:
            # Extract parameters
            max_tokens = kwargs.get('max_tokens', 1000)
            temperature = kwargs.get('temperature', 0.7)
            
            # Call Groq API
            response_text = await self.groq_client.chat(
                messages=messages,
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # Return in OpenAI-compatible format for AutoGen
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": sum(len(msg.get("content", "")) for msg in messages) // 4,
                    "completion_tokens": len(response_text) // 4,
                    "total_tokens": (sum(len(msg.get("content", "")) for msg in messages) + len(response_text)) // 4
                }
            }
            
        except Exception as e:
            logger.error("Groq LLM client error", error=str(e))
            # Return error response
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"Error generating response: {str(e)}"
                    },
                    "finish_reason": "error"
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }


class GroqAutogenClient:
    """
    Groq client for multi-agent conversations.
    Provides a simple interface for agent-to-agent communication.
    """
    
    def __init__(self, model: str = "llama-3.1-8b-instant", **kwargs):
        self.groq_client = GroqClient()
        self._model = model
        
    async def create(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """
        Create completion using Groq API.
        
        Args:
            messages: Conversation messages
            **kwargs: Additional parameters
            
        Returns:
            Response object compatible with AutoGen
        """
        try:
            # Extract parameters
            max_tokens = kwargs.get('max_tokens', 1000)
            temperature = kwargs.get('temperature', 0.7)
            
            logger.debug("Creating Groq completion", 
                        model=self._model,
                        messages_count=len(messages),
                        max_tokens=max_tokens)
            
            # Call Groq API
            response_text = await self.groq_client.chat(
                messages=messages,
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            logger.debug("Groq completion successful", 
                        response_length=len(response_text))
            
            # Create response object that mimics OpenAI format
            class GroqResponse:
                def __init__(self, content: str):
                    self.choices = [
                        type('Choice', (), {
                            'message': type('Message', (), {
                                'content': content,
                                'role': 'assistant'
                            })(),
                            'finish_reason': 'stop'
                        })()
                    ]
                    self.usage = type('Usage', (), {
                        'prompt_tokens': sum(len(msg.get("content", "")) for msg in messages) // 4,
                        'completion_tokens': len(content) // 4,
                        'total_tokens': (sum(len(msg.get("content", "")) for msg in messages) + len(content)) // 4
                    })()
            
            return GroqResponse(response_text)
            
        except Exception as e:
            logger.error("Groq AutoGen client error", error=str(e))
            
            # Return error response
            class ErrorResponse:
                def __init__(self, error_msg: str):
                    self.choices = [
                        type('Choice', (), {
                            'message': type('Message', (), {
                                'content': f"Error: {error_msg}",
                                'role': 'assistant'
                            })(),
                            'finish_reason': 'error'
                        })()
                    ]
                    self.usage = type('Usage', (), {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    })()
            
            return ErrorResponse(str(e))