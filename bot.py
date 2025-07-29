import discord
import asyncio
import json
import os
import traceback
import google.generativeai as genai
from typing import Optional, List
from discord.ext import commands
from config import Config
from ratelimiter import RateLimiter
from logger import logger

class SummarizerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        
        super().__init__(
            command_prefix='!',
            help_command=None,
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Use !summarize or !summarize <count> | !help for info"
            )
        )
        
        self.rate_limiter = RateLimiter()
        self.config = Config()
        
        # Initialize Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    async def on_ready(self):
        """Bot ready event"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Connected to {len(self.guilds)} guilds')
    
    async def on_message(self, message):
        """Process commands"""
        await self.process_commands(message)
    
    async def on_command_error(self, ctx, error):
        """Global command error handler"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"Command error in {ctx.command}: {error}")
        logger.error(traceback.format_exc())
        
        await ctx.send("An error occurred while processing your request. Please try again later.")
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 characters for English)"""
        return len(text) // 4
    
    async def get_messages_since_user_activity(self, channel, user_id: int, limit: int = 1000) -> List[discord.Message]:
        """Get messages by enumerating back until we find the calling user or hit limit"""
        messages = []
        found_user = False
        
        logger.info(f"Looking for messages since user {user_id} was last active (limit: {limit})")
        
        async for message in channel.history(limit=limit):
            # Add message to our collection
            messages.append(message)
            
            # Check if this message is from the calling user (and not the command itself)
            if message.author.id == user_id and not message.content.startswith('!'):
                logger.info(f"Found user's last non-command message at {message.created_at}")
                found_user = True
                break
        
        if not found_user:
            logger.info(f"Did not find user's previous activity within {limit} messages, using all collected messages")
        
        # Remove the user's last message from the summary (we don't need to summarize back to their own message)
        if found_user and messages:
            messages = messages[:-1]  # Remove the last message (user's previous message)
        
        logger.info(f"Returning {len(messages)} messages for summarization")
        return messages[::-1]  # Reverse to chronological order
    
    def format_messages_for_ai(self, messages: List[discord.Message]) -> str:
        """Format messages for AI processing"""
        if not messages:
            return "No messages to summarize."
        
        formatted_lines = []
        prev_time = None
        
        for message in messages:
            # Check for time gaps
            if prev_time and (message.created_at - prev_time).total_seconds() > self.config.get('time_gap_threshold_minutes') * 60:
                formatted_lines.append("\n--- TIME GAP ---\n")
            
            # Format: Display Name | Message Content | Timestamp
            display_name = message.author.display_name or message.author.name
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = message.content or "[No text content]"
            
            # Handle attachments
            if message.attachments:
                attachment_info = f" [Attachments: {', '.join(att.filename for att in message.attachments)}]"
                content += attachment_info
            
            formatted_lines.append(f"{display_name} | {content} | {timestamp}")
            prev_time = message.created_at
        
        return "\n".join(formatted_lines)
    
    async def generate_summary(self, formatted_messages: str) -> str:
        """Generate summary using Gemini AI"""
        full_prompt = f"{self.config.get('system_prompt')}\n\nMessages to summarize:\n{formatted_messages}"
        
        # Check token limits
        estimated_tokens = self.estimate_tokens(full_prompt)
        if estimated_tokens > 1000000:  # Leave buffer for 1M token limit
            return "Error: Message history too long to summarize. Try with fewer messages."
        
        # Check rate limits
        if not await self.rate_limiter.can_make_request(estimated_tokens):
            logger.warning("Rate limit would be exceeded, denying request")
            return "Rate limit reached. Please wait before making another request."
        
        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt
            )
            
            # Record successful request
            self.rate_limiter.record_request(estimated_tokens + self.estimate_tokens(response.text))
            
            logger.info(f"Generated summary with ~{estimated_tokens} input tokens")
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            logger.error(traceback.format_exc())
            return f"Error generating summary: {str(e)}"

# Create bot instance
bot = SummarizerBot()

@bot.command(name='summarize', aliases=["summarise"])
async def summarize(ctx, count: Optional[int] = None):
    """Summarize recent messages or messages since user was last active"""
    async with ctx.typing():
        try:
            if count is not None:
                # Validate count
                if count <= 5:
                    await ctx.send("Message count must be at least 5.")
                    return
                if count > bot.config.get('max_messages_limit'):
                    await ctx.send(f"Maximum message count is {bot.config.get('max_messages_limit')}.")
                    return
                
                # Get specific number of messages
                messages = []
                async for message in ctx.channel.history(limit=count):
                    messages.append(message)
                messages = messages[::-1]  # Reverse to chronological order
                
                logger.info(f"Summarizing {len(messages)} messages by request from {ctx.author}")
            else:
                # Get messages since user was last active
                messages = await bot.get_messages_since_user_activity(
                    ctx.channel, 
                    ctx.author.id,
                    bot.config.get('max_messages_default')
                )
                logger.info(f"Summarizing {len(messages)} messages since last activity from {ctx.author}")
            
            if not messages:
                await ctx.send("No messages found to summarize.")
                return
            
            # Format and generate summary
            formatted_messages = bot.format_messages_for_ai(messages)
            summary = await bot.generate_summary(formatted_messages)
            
            # Split long summaries if needed
            if len(summary) > 2000:
                # Discord message limit is 2000 characters
                chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"**Summary of {len(messages)} messages:**\n{chunk}")
                    else:
                        await ctx.send(chunk)
            else:
                await ctx.send(f"**Summary of {len(messages)} messages:**\n{summary}")
                
        except Exception as e:
            logger.error(f"Error in summarize command: {e}")
            logger.error(traceback.format_exc())
            await ctx.send("An error occurred while generating the summary.")

@bot.command(name='config')
@commands.has_permissions(administrator=True)
async def config_command(ctx, key: str = None, *, value: str = None):
    """Configure bot settings (Admin only)"""
    if key is None:
        # Show current config
        config_text = "**Current Configuration:**\n```json\n"
        config_text += json.dumps(bot.config.config, indent=2)
        config_text += "\n```"
        await ctx.send(config_text)
        return
    
    if value is None:
        # Show specific config value
        current_value = bot.config.get(key)
        if current_value is not None:
            await ctx.send(f"**{key}:** {current_value}")
        else:
            await ctx.send(f"Configuration key '{key}' not found.")
        return
    
    # Set config value
    try:
        # Try to parse as JSON for complex types
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value
        
        bot.config.set(key, parsed_value)
        await ctx.send(f"Configuration updated: **{key}** = {parsed_value}")
        logger.info(f"Config updated by {ctx.author}: {key} = {parsed_value}")
        
    except Exception as e:
        await ctx.send(f"Error updating configuration: {e}")

@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    help_embed = discord.Embed(
        title="AI Text Summarizer Bot",
        description="Summarize Discord conversations using AI",
        color=0x00ff00
    )
    
    help_embed.add_field(
        name="Commands",
        value=(
            "`!summarize` - Summarize messages since you were last active\n"
            "`!summarize <count>` - Summarize the last <count> messages\n"
            "`!config` - View current configuration (Admin)\n"
            "`!config <key>` - View specific config value (Admin)\n"
            "`!config <key> <value>` - Set config value (Admin)\n"
            "`!help` - Show this help message"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="Rate Limits",
        value="The bot has built-in rate limiting to prevent API overuse.",
        inline=False
    )
    
    help_embed.set_footer(text="Powered by Google Gemini AI")
    
    await ctx.send(embed=help_embed)

# Error handler for missing permissions
@config_command.error
async def config_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need administrator permissions to use this command.")

if __name__ == "__main__":
    # Check for required environment variables
    if not os.getenv('DISCORD_TOKEN'):
        logger.error("DISCORD_TOKEN environment variable not set")
        exit(1)
    
    if not os.getenv('GEMINI_API_KEY'):
        logger.error("GEMINI_API_KEY environment variable not set")
        exit(1)
    
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        logger.error(traceback.format_exc())