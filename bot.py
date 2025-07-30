import discord
import asyncio
import json
import os
import traceback
import hashlib
import secrets
import google.generativeai as genai
from typing import Optional, List, Set
from discord.ext import commands
from config import Config
from ratelimiter import RateLimiter
from logger import logger

class SummarizerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guilds = True
        
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
        
        # Privacy features
        self.salt = self._load_or_create_salt()
        self.opted_out_users: Set[str] = set()  # Will store hashed user IDs
        self._load_opted_out_users()
        
        # Initialize Gemini
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    def _load_or_create_salt(self) -> str:
        """Load existing salt or create a new one for hashing user IDs"""
        salt_file = 'bot_salt.txt'
        try:
            if os.path.exists(salt_file):
                with open(salt_file, 'r') as f:
                    return f.read().strip()
            else:
                # Create new salt
                salt = secrets.token_hex(32)
                with open(salt_file, 'w') as f:
                    f.write(salt)
                logger.info("Created new salt for user ID hashing")
                return salt
        except Exception as e:
            logger.error(f"Error handling salt file, exiting early: {e}")
            logger.error(traceback.format_exc())
            quit()
    
    def _hash_user_id(self, user_id: int) -> str:
        """Hash a user ID with salt for privacy"""
        return hashlib.sha256(f"{user_id}{self.salt}".encode()).hexdigest()
    
    def _load_opted_out_users(self):
        """Load opted-out users from config"""
        opted_out = self.config.get('opted_out_users')
        if opted_out:
            self.opted_out_users = set(opted_out)
            logger.info(f"Loaded {len(self.opted_out_users)} opted-out users")
    
    def _save_opted_out_users(self):
        """Save opted-out users to config"""
        self.config.set('opted_out_users', list(self.opted_out_users))
    
    def _is_user_opted_out(self, user_id: int) -> bool:
        """Check if a user has opted out"""
        hashed_id = self._hash_user_id(user_id)
        return hashed_id in self.opted_out_users
    
    async def on_ready(self):
        """Bot ready event"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Connected to {len(self.guilds)} guilds')
    
    async def on_guild_join(self, guild):
        """Send welcome message when bot joins a new guild"""
        await self._send_welcome_message(guild)
    
    async def _send_welcome_message(self, guild):
        """Send welcome message to a guild's system channel or first available channel"""
        try:
            target_channel = None
            
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                target_channel = guild.system_channel
            
            if not target_channel:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        if any(name in channel.name.lower() for name in ['general', 'main', 'chat', 'welcome']):
                            target_channel = channel
                            break
            
            if not target_channel:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        target_channel = channel
                        break
            
            if target_channel:
                embed = discord.Embed(
                    title="ShortCord Summarizer Bot",
                    description="Welcome! I can help you summarize Discord conversations using AI.",
                    color=0x00ff00
                )
                
                embed.add_field(
                    name="What I Do",
                    value=(
                        "I analyze chat messages and create concise summaries of conversations. "
                        "Use `!help` to see all available commands."
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Privacy Information",
                    value=(
                        "• **No Message Storage**: I do not store user messages or generated summaries\n"
                        "• **External API**: Message data is sent to Google's Gemini AI for processing\n"
                        "• **Opt-Out Available**: Use `!optout` to exclude your messages from summaries\n"
                        "• **Opt-In**: Use `!optin` to re-enable summary inclusion"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Legal",
                    value=(
                        "By using channels where this bot is present, you agree to our:\n"
                        "• [Terms of Service](https://example.com/terms)\n"
                        "• [Privacy Policy](https://example.com/privacy)\n"
                    ),
                    inline=False
                )
                
                embed.set_footer(text="Use !help for command information | Powered by Google Gemini AI")
                
                await target_channel.send(embed=embed)
                logger.info(f"Sent welcome message to {guild.name} in #{target_channel.name}")
                
        except Exception as e:
            logger.error(f"Failed to send welcome message to {guild.name}: {e}")
    
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
        """Format messages for AI processing, excluding opted-out users"""
        if not messages:
            return "No messages to summarize."
        
        formatted_lines = []
        prev_time = None
        excluded_count = 0
        
        for message in messages:
            # Skip messages from opted-out users
            if self._is_user_opted_out(message.author.id):
                excluded_count += 1
                continue
            
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
        
        if excluded_count > 0:
            logger.info(f"Excluded {excluded_count} messages from opted-out users")
        
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
                if count < 5:
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
            
            # Check if there are any messages left after filtering opted-out users
            if not formatted_messages.strip() or formatted_messages.strip() == "No messages to summarize.":
                await ctx.send("No messages available to summarize after privacy filtering.")
                return
            
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

@bot.command(name='optout')
async def opt_out(ctx):
    """Opt out of message summarization"""
    try:
        hashed_id = bot._hash_user_id(ctx.author.id)
        
        if hashed_id in bot.opted_out_users:
            await ctx.send("You are already opted out of message summarization.")
            return
        
        bot.opted_out_users.add(hashed_id)
        bot._save_opted_out_users()
        
        embed = discord.Embed(
            title="Opted Out Successfully",
            description="Your messages will no longer be included in summaries.",
            color=0xff9900
        )
        embed.add_field(
            name="What this means:",
            value=(
                "• Your messages won't be sent to Google's AI for processing\n"
                "• Your messages won't appear in any generated summaries\n"
                "• You can opt back in anytime using `!optin`"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
        logger.info(f"A user opted out of summarization")
        
    except Exception as e:
        logger.error(f"Error in opt_out command: {e}")
        await ctx.send("An error occurred while processing your opt-out request.")

@bot.command(name='optin')
async def opt_in(ctx):
    """Opt back into message summarization"""
    try:
        hashed_id = bot._hash_user_id(ctx.author.id)
        
        if hashed_id not in bot.opted_out_users:
            await ctx.send("You are not currently opted out of message summarization.")
            return
        
        bot.opted_out_users.remove(hashed_id)
        bot._save_opted_out_users()
        
        embed = discord.Embed(
            title="Opted In Successfully",
            description="Your messages will now be included in summaries again.",
            color=0x00ff00
        )
        embed.add_field(
            name="What this means:",
            value=(
                "• Your messages may be sent to Google's AI for processing\n"
                "• Your messages may appear in generated summaries\n"
                "• You can opt out anytime using `!optout`"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
        logger.info(f"User {ctx.author} ({ctx.author.id}) opted back into summarization")
        
    except Exception as e:
        logger.error(f"Error in opt_in command: {e}")
        await ctx.send("An error occurred while processing your opt-in request.")

@bot.command(name='config')
@commands.has_permissions(administrator=True)
async def config_command(ctx, key: str = None, *, value: str = None):
    """Configure bot settings (Admin only)"""
    # Prevent editing of opted_out_users via config command
    if key == 'opted_out_users':
        await ctx.send("User opt-out data cannot be modified through the config command for privacy reasons.")
        return
    
    if key is None:
        # Show current config (excluding sensitive data)
        config_copy = bot.config.config.copy()
        if 'opted_out_users' in config_copy:
            config_copy['opted_out_users'] = f"[{len(config_copy['opted_out_users'])} opted-out users]"
        
        config_text = "**Current Configuration:**\n```json\n"
        config_text += json.dumps(config_copy, indent=2)
        config_text += "\n```"
        await ctx.send(config_text)
        return
    
    if value is None:
        # Show specific config value (excluding sensitive data)
        if key == 'opted_out_users':
            await ctx.send(f"**{key}:** [{len(bot.config.get(key) or [])} opted-out users] (hashed data not shown)")
            return
        
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
        name="Summarization Commands",
        value=(
            "`!summarize` - Summarize messages since you were last active\n"
            "`!summarize <count>` - Summarize the last <count> messages"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="Privacy Commands",
        value=(
            "`!optout` - Exclude your messages from all summaries\n"
            "`!optin` - Re-include your messages in summaries"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="Admin Commands",
        value=(
            "`!config` - View current configuration\n"
            "`!config <key>` - View specific config value\n"
            "`!config <key> <value>` - Set config value"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="Privacy Information",
        value=(
            "• Messages are sent to Google's Gemini AI for processing\n"
            "• No messages or summaries are stored by this bot\n"
            "• Use `!optout` to exclude your messages from processing\n"
            "• View our [Terms](https://example.com/terms) and [Privacy Policy](https://example.com/privacy)"
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