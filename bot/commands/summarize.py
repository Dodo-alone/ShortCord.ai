"""
Summarization commands
"""

import traceback
from typing import Optional
from discord.ext import commands
from google.genai import types

from core.logger import logger
from bot.utils.validation_utils import validate_message_count
from bot.utils.text_utils import smart_split_message
from bot.handlers.message_handler import MessageProcessor


class SummarizeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_processor = MessageProcessor(bot.privacy_manager)
    
    @commands.command(name='summarize', aliases=["summarise", "Summarize", "Summarise"])
    async def summarize(self, ctx, count: Optional[int] = None):
        """Summarize recent messages or messages since user was last active"""
        async with ctx.typing():
            try:
                if count is not None:
                    # Validate count
                    is_valid, error_msg = validate_message_count(count)
                    if not is_valid:
                        await ctx.send(error_msg)
                        return
                    
                    # Get specific number of messages
                    messages = []
                    async for message in ctx.channel.history(limit=count+1):
                        messages.append(message)
                    messages = messages[:0:-1]  # Reverse to chronological order
                    
                    logger.info(f"Summarizing {len(messages)} messages by request from {ctx.author}")
                else:
                    # Get messages since user was last active
                    messages = await self.message_processor.get_messages_since_user_activity(
                        ctx.channel, 
                        ctx.author.id,
                        self.bot.config.get('max_messages_default')
                    )
                    logger.info(f"Summarizing {len(messages)} messages since last activity from {ctx.author}")
                
                if not messages:
                    await ctx.send("No messages found to summarize.")
                    return
                
                # Format messages with interlaced media
                content_parts = await self.message_processor.format_messages_for_ai_interlaced(messages)
                
                # Check if there are any messages left after filtering opted-out users
                if not content_parts or len(content_parts) <= 1:  # Only the instruction part
                    await ctx.send("No messages available to summarize after privacy filtering.")
                    return
                
                summary = await self.bot.ai_service.generate_summary(content_parts)
                
                # Count media parts for display
                media_count = sum(1 for part in content_parts if isinstance(part, types.Part))
                
                # Smart splitting for long summaries
                if len(summary) >= 2000:
                    chunks = smart_split_message(summary, max_length=1900)  # Leave buffer for headers
                    
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            media_note = f" (including {media_count} media files)" if media_count > 0 else ""
                            header = f"**Summary of {len(messages)} messages{media_note}:**\n"
                            
                            # Check if header + chunk exceeds limit
                            if len(header + chunk) > 2000:
                                await ctx.send(header.rstrip())  # Send header separately
                                await ctx.send(chunk)
                            else:
                                await ctx.send(header + chunk)
                        else:
                            await ctx.send(chunk)
                else:
                    media_note = f" (including {media_count} media files)" if media_count > 0 else ""
                    await ctx.send(f"**Summary of {len(messages)} messages{media_note}:**\n{summary}")
                    
            except Exception as e:
                logger.error(f"Error in summarize command: {e}")
                logger.error(traceback.format_exc())
                await ctx.send("An error occurred while generating the summary.")


async def setup(bot):
    await bot.add_cog(SummarizeCog(bot))