import discord
from discord.ext import commands
import google.generativeai as genai
import asyncio
import logging
from datetime import datetime, timedelta
import json
import os
from typing import Optional, List, Dict
import time
from collections import deque
import traceback


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SummarizerBot')

class RateLimiter:
    """Rate limiter for Gemini API calls"""
    def __init__(self):
        # Gemini 2.5 Flash Lite limits: 15 req/min, 250k tokens/min, 1k req/day
        self.requests_per_minute = deque(maxlen=15)
        self.tokens_per_minute = deque(maxlen=250000)
        self.requests_per_day = deque(maxlen=1000)
        
    async def can_make_request(self, estimated_tokens: int = 1000) -> bool:
        """Check if we can make a request without hitting rate limits"""
        now = time.time()
        
        # Clean old entries
        minute_ago = now - 60
        day_ago = now - 86400
        
        # Remove entries older than 1 minute
        while self.requests_per_minute and self.requests_per_minute[0] < minute_ago:
            self.requests_per_minute.popleft()
        
        # Remove tokens older than 1 minute
        while self.tokens_per_minute and self.tokens_per_minute[0]['time'] < minute_ago:
            self.tokens_per_minute.popleft()
            
        # Remove requests older than 1 day
        while self.requests_per_day and self.requests_per_day[0] < day_ago:
            self.requests_per_day.popleft()
        
        # Check limits
        current_tokens = sum(entry['tokens'] for entry in self.tokens_per_minute)
        
        if (len(self.requests_per_minute) >= 14 or  # Leave buffer
            current_tokens + estimated_tokens > 240000 or  # Leave buffer
            len(self.requests_per_day) >= 950):  # Leave buffer
            return False
            
        return True
    
    def record_request(self, tokens_used: int):
        """Record a successful request"""
        now = time.time()
        self.requests_per_minute.append(now)
        self.tokens_per_minute.append({'time': now, 'tokens': tokens_used})
        self.requests_per_day.append(now)

class Config:
    """Configuration management"""
    def __init__(self, config_file: str = 'config.json'):
        self.config_file = config_file
        self.default_config = {
            "system_prompt": """You are a helpful Discord chat summarizer. Your task is to create concise, informative summaries of Discord conversations.

Guidelines:
- Identify distinct conversation topics and threads
- Note when conversations are separated by significant time gaps (treat as separate discussions)
- Highlight key decisions, announcements, or important information
- Maintain context about who said what when relevant
- Use clear, readable formatting with bullet points for multiple topics
- Keep summaries concise but comprehensive
- If there are inside jokes or references, briefly explain them if context allows
- Note the time span of the conversation being summarized

Format your response as a clean summary without excessive technical language.""",
            "max_messages_default": 50,
            "max_messages_limit": 200,
            "time_gap_threshold_minutes": 30
        }
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults for any missing keys
                for key, value in self.default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                self.save_config(self.default_config)
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self.default_config.copy()
    
    def save_config(self, config: dict):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get(self, key: str):
        """Get configuration value"""
        return self.config.get(key)
    
    def set(self, key: str, value):
        """Set configuration value"""
        self.config[key] = value
        self.save_config(self.config)

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
        self.user_last_activity = {}  # Track user last activity
        
        # Initialize Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    async def on_ready(self):
        """Bot ready event"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Connected to {len(self.guilds)} guilds')
    
    async def on_message(self, message):
        """Track user activity and process commands"""
        if not message.author.bot:
            self.user_last_activity[message.author.id] = message.created_at
        
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
    
    async def get_messages_until_last_active(self, channel, user_id: int, limit: int = 1000) -> List[discord.Message]:
        """Get messages from when user was last active"""
        if user_id not in self.user_last_activity:
            # If no activity tracked, get recent messages
            messages = []
            async for message in channel.history(limit=min(limit, 100)):
                messages.append(message)
            return messages[::-1]  # Reverse to chronological order
        
        last_active = self.user_last_activity[user_id]
        messages = []
        
        async for message in channel.history(limit=limit, after=last_active):
            messages.append(message)
        
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

@bot.command(name='summarize')
async def summarize(ctx, count: Optional[int] = None):
    """Summarize recent messages or messages since user was last active"""
    async with ctx.typing():
        try:
            if count is not None:
                # Validate count
                if count <= 0:
                    await ctx.send("Message count must be positive.")
                    return
                if count > bot.config.get('max_messages_limit'):
                    await ctx.send(f"Maximum message count is {bot.config.get('max_messages_limit')}.")
                    return
                if count < 5:
                    await ctx.send("Message count must be more than 5.")
                    return
                
                # Get specific number of messages
                messages = []
                async for message in ctx.channel.history(limit=count):
                    messages.append(message)
                messages = messages[::-1]  # Reverse to chronological order
                
                logger.info(f"Summarizing {len(messages)} messages by request from {ctx.author}")
            else:
                # Get messages since user was last active
                messages = await bot.get_messages_until_last_active(
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