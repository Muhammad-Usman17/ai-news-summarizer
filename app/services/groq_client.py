import httpx
from typing import Dict, Any, Optional, List
import json
import os

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext

logger = get_logger(__name__)
settings = get_settings()


class GroqClient:
    """Client for interacting with Groq API for fast LLM inference."""
    
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.base_url = "https://api.groq.com/openai/v1"
        self.default_model = "llama-3.1-8b-instant"  # Fast Llama3 model
        self.timeout = 30  # Groq is much faster than local Ollama
        
    async def generate(
        self, 
        prompt: str, 
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate text using Groq API.
        
        Args:
            prompt: Input prompt
            model: Model name (defaults to configured model)
            max_tokens: Maximum tokens to generate
            temperature: Generation temperature
            **kwargs: Additional generation parameters
            
        Returns:
            Generated text response
        """
        model = model or self.default_model
        
        with LogContext(model=model, prompt_length=len(prompt)):
            logger.debug("Generating text with Groq")
            
            # Convert to chat format for Groq
            messages = [{"role": "user", "content": prompt}]
            
            return await self.chat(messages, model, max_tokens, temperature, **kwargs)
    
    async def chat(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Chat completion using Groq API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name (defaults to configured model)
            max_tokens: Maximum tokens to generate
            temperature: Generation temperature
            **kwargs: Additional parameters
            
        Returns:
            Assistant response
        """
        model = model or self.default_model
        
        with LogContext(model=model, messages_count=len(messages)):
            logger.debug("Starting chat with Groq")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
                **kwargs
            }
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    # Log usage statistics
                    usage = result.get("usage", {})
                    logger.debug("Groq chat completed successfully", 
                               response_length=len(content),
                               prompt_tokens=usage.get("prompt_tokens"),
                               completion_tokens=usage.get("completion_tokens"))
                    
                    return content
                    
            except httpx.TimeoutException:
                logger.error("Groq request timed out")
                raise Exception(f"Groq request timed out after {self.timeout}s")
            except httpx.HTTPStatusError as e:
                logger.error("Groq HTTP error", status_code=e.response.status_code)
                try:
                    error_detail = e.response.json()
                    logger.error("Groq error details", error=error_detail)
                except:
                    pass
                raise Exception(f"Groq API error: {e.response.status_code}")
            except KeyError as e:
                logger.error("Unexpected Groq response format", error=str(e))
                raise Exception(f"Unexpected Groq response format: {str(e)}")
            except Exception as e:
                logger.error("Groq generation failed", error=str(e))
                raise Exception(f"Groq generation failed: {str(e)}")
    
    async def check_health(self) -> bool:
        """
        Check if Groq service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple test with available models endpoint first
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10) as client:
                # Try to list models as a health check
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers
                )
                response.raise_for_status()
                
                # If that works, try a simple chat completion
                test_payload = {
                    "model": self.default_model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                    "temperature": 0.0
                }
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=test_payload,
                    headers=headers
                )
                response.raise_for_status()
                
                logger.info("Groq health check passed")
                return True
                
        except Exception as e:
            logger.error("Groq health check failed", error=str(e))
            return False
    
    async def list_models(self) -> List[str]:
        """
        List available Groq models.
        
        Returns:
            List of model names
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers
                )
                response.raise_for_status()
                
                result = response.json()
                models = [model["id"] for model in result.get("data", [])]
                
                logger.debug("Listed Groq models", count=len(models))
                return models
                
        except Exception as e:
            logger.error("Failed to list Groq models", error=str(e))
            return []
    
    def get_fast_model(self) -> str:
        """Get the fastest available model for quick summaries."""
        return "llama-3.1-8b-instant"  # Very fast model
    
    def get_quality_model(self) -> str:
        """Get a higher quality model for better summaries."""
        return "llama-3.3-70b-versatile"  # Higher quality but still fast
    
    def get_smart_model(self) -> str:
        """Get a smart model for analysis and critique tasks."""
        return "llama-3.3-70b-versatile"  # Higher reasoning capabilities