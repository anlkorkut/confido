import asyncio
import logging
from typing import Dict, List, Iterator, Optional, Any, Callable
import time
from functools import wraps

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

# Standalone retry decorator that doesn't depend on class instance
def retry_with_exponential_backoff(max_retries: int = 3):
    """Decorator for retry logic with exponential backoff"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_count = 0
            base_wait_time = 1  # Start with 1 second wait
            max_wait_time = 16  # Maximum wait time in seconds
            logger = logging.getLogger(__name__)
            
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(f"Failed after {max_retries} retries: {str(e)}")
                        raise
                    
                    # Calculate wait time with exponential backoff and jitter
                    wait_time = min(base_wait_time * (2 ** (retry_count - 1)), max_wait_time)
                    jitter = wait_time * 0.1  # 10% jitter
                    wait_time = wait_time + (jitter * (time.time() % 1))
                    
                    logger.warning(f"Retry {retry_count}/{max_retries} after error: {str(e)}. Waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
        return wrapper
    return decorator

class OpenAIWrapper:
    def __init__(self, api_key: str, model: str = "gpt-4o", temperature: float = 0.7):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.logger = logging.getLogger(__name__)
        
    @retry_with_exponential_backoff()
    async def chat_complete(self, messages: List[Dict[str, str]], **params) -> str:
        """Complete chat with retry logic and error handling"""
        try:
            # Merge default parameters with provided ones
            merged_params = {
                "model": self.model,
                "temperature": self.temperature,
            }
            merged_params.update(params)
            
            # Make API call
            response = await self.client.chat.completions.create(
                messages=messages,
                **merged_params
            )
            
            # Extract and return response text
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error in chat completion: {str(e)}")
            raise
    
    @retry_with_exponential_backoff()
    async def chat_stream(self, messages: List[Dict[str, str]], **params) -> Iterator[str]:
        """Stream chat responses"""
        try:
            # Merge default parameters with provided ones
            merged_params = {
                "model": self.model,
                "temperature": self.temperature,
                "stream": True,
            }
            merged_params.update(params)
            
            # Make streaming API call
            stream = await self.client.chat.completions.create(
                messages=messages,
                **merged_params
            )
            
            # Process and yield streaming responses
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            self.logger.error(f"Error in chat streaming: {str(e)}")
            raise
    
    @retry_with_exponential_backoff()
    async def function_call(self, messages: List[Dict[str, str]], functions: List[Dict], **params) -> Dict:
        """Execute function calls"""
        try:
            # Merge default parameters with provided ones
            merged_params = {
                "model": self.model,
                "temperature": self.temperature,
            }
            merged_params.update(params)
            
            # Make API call with function definitions
            response = await self.client.chat.completions.create(
                messages=messages,
                functions=functions,
                **merged_params
            )
            
            # Process function call response
            message = response.choices[0].message
            
            if message.function_call:
                return {
                    "name": message.function_call.name,
                    "arguments": message.function_call.arguments,
                    "response": message.content
                }
            else:
                return {"response": message.content}
        except Exception as e:
            self.logger.error(f"Error in function call: {str(e)}")
            raise