"""
AI service handler for Gemini integration
"""

import os
import asyncio
import traceback
from typing import List
import google.genai as genai
from google.genai import types

from core.config import Config
from core.rate_limiter import RateLimiter
from core.logger import logger


class AIService:
    def __init__(self):
        self.config = Config()
        self.rate_limiter = RateLimiter()
        
        # Initialize Gemini with new API
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    
    async def estimate_tokens_with_content_parts(self, content_parts: List) -> int:
        """Estimate tokens for interlaced content parts using Gemini's count_tokens"""
        try:
            if not content_parts:
                return 0
            
            # Use Gemini's token counting
            count_result = await asyncio.to_thread(
                self.client.models.count_tokens,
                model='gemini-2.5-flash',
                contents=[content_parts]
            )
            
            total_tokens = count_result.total_tokens
            media_count = sum(1 for part in content_parts if isinstance(part, types.Part))
            logger.info(f"Estimated {total_tokens} tokens for content with {media_count} media parts")
            return total_tokens
            
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            # Fallback to simple estimation
            estimated = 0
            for part in content_parts:
                if isinstance(part, str):
                    estimated += len(part) // 4
                elif isinstance(part, types.Part):
                    # Add rough estimates for media
                    if hasattr(part, 'mime_type'):
                        if part.mime_type.startswith('image'):
                            estimated += 500  # Rough estimate for images
                        elif part.mime_type.startswith('video'):
                            estimated += 2000  # Rough estimate for videos
                        elif part.mime_type.startswith('audio'):
                            estimated += 1000  # Rough estimate for audio
            
            logger.warning(f"Using fallback token estimation: {estimated}")
            return estimated
    
    async def generate_summary(self, content_parts: List) -> str:
        """Generate summary using Gemini AI with interlaced multimodal content"""
        # Check if we have any content
        if not content_parts:
            return "No content available to summarize."
        
        # Check token limits
        estimated_tokens = await self.estimate_tokens_with_content_parts(content_parts)
        if estimated_tokens > 1000000:  # Conservative limit for 1M context
            return "Error: Message history too long to summarize. Try with fewer messages."
        
        # Check rate limits
        if not await self.rate_limiter.can_make_request(estimated_tokens):
            logger.warning("Rate limit would be exceeded, denying request")
            return "Rate limit reached. Please wait before making another request."
        
        try:
            # Create the request using the new API structure
            request = {
                "model": "gemini-2.5-flash-lite",
                "config": types.GenerateContentConfig(
                    system_instruction=self.config.get('system_prompt'),
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    temperature=1
                ),
                "contents": [content_parts]
            }
            
            # Generate content using the new API
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                **request
            )
            
            # Extract the response text
            response_text = response.candidates[0].content.parts[0].text
            
            # Record successful request (estimate response tokens)
            response_tokens = response.usage_metadata.candidates_token_count
            if response_tokens is None: 
                response_tokens = 0
            self.rate_limiter.record_request(estimated_tokens + response_tokens)
            
            media_count = sum(1 for part in content_parts if isinstance(part, types.Part))
            logger.info(f"Generated summary with ~{estimated_tokens} input tokens and {media_count} interlaced media parts")
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            logger.error(traceback.format_exc())
            return f"Error generating summary: {str(e)}"