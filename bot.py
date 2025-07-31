import discord
import asyncio
import json
import os
import traceback
import hashlib
import secrets
import aiohttp
import google.genai as genai
from google.genai import types
from typing import Optional, List, Set, Tuple, Dict
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
        
        # Initialize Gemini with new API
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        
        # Supported media types
        self.supported_image_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
        self.supported_video_types = {'video/mp4', 'video/mpeg', 'video/quicktime', 'video/webm'}
        self.supported_audio_types = {'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/webm'}
        
        # File size limits (in bytes)
        self.max_file_size = 20 * 1024 * 1024  # 20MB general limit
        self.max_video_size = 100 * 1024 * 1024  # 100MB for video
    
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
    
    def _get_mime_type(self, filename: str) -> Optional[str]:
        """Get MIME type from file extension"""
        ext = filename.lower().split('.')[-1]
        mime_map = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp',
            'mp4': 'video/mp4', 'mov': 'video/quicktime', 'webm': 'video/webm',
            'mpeg': 'video/mpeg', 'mpg': 'video/mpeg',
            'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg',
            'weba': 'audio/webm', 'm4a': 'audio/mp4'
        }
        return mime_map.get(ext)
    
    def _is_supported_media(self, mime_type: str) -> bool:
        """Check if the media type is supported by Gemini"""
        return (mime_type in self.supported_image_types or 
                mime_type in self.supported_video_types or 
                mime_type in self.supported_audio_types)
    
    async def _download_attachment(self, attachment: discord.Attachment) -> Optional[Tuple[bytes, str]]:
        """Download attachment and return bytes with mime type"""
        try:
            # Check file size limits
            max_size = self.max_video_size if attachment.content_type and 'video' in attachment.content_type else self.max_file_size
            if attachment.size > max_size:
                logger.warning(f"Attachment {attachment.filename} too large: {attachment.size} bytes")
                return None
            
            # Get MIME type
            mime_type = attachment.content_type or self._get_mime_type(attachment.filename)
            if not mime_type or not self._is_supported_media(mime_type):
                logger.info(f"Unsupported media type for {attachment.filename}: {mime_type}")
                return None
            
            # Download the file
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        data = await response.read()
                        logger.info(f"Downloaded {attachment.filename}: {len(data)} bytes, type: {mime_type}")
                        return data, mime_type
                    else:
                        logger.error(f"Failed to download {attachment.filename}: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading attachment {attachment.filename}: {e}")
            return None
    
    async def _process_embeds(self, message: discord.Message) -> List[str]:
        """Process embeds and extract useful information"""
        embed_info = []
        
        for embed in message.embeds:
            embed_text = []
            
            if embed.title:
                embed_text.append(f"**Embed Title:** {embed.title}")
            
            if embed.description:
                embed_text.append(f"**Embed Description:** {embed.description}")
            
            if embed.url:
                embed_text.append(f"**Embed URL:** {embed.url}")
            
            # Process embed fields
            for field in embed.fields:
                embed_text.append(f"**{field.name}:** {field.value}")
            
            # Handle embed images/videos
            if embed.image:
                embed_text.append(f"**Embed Image:** {embed.image.url}")
            
            if embed.video:
                embed_text.append(f"**Embed Video:** {embed.video.url}")
            
            if embed.thumbnail:
                embed_text.append(f"**Embed Thumbnail:** {embed.thumbnail.url}")
            
            if embed_text:
                embed_info.append("\n".join(embed_text))
        
        return embed_info
    
    def _process_reactions(self, message: discord.Message) -> str:
        """Process message reactions and return formatted string"""
        if not message.reactions:
            return ""
        
        reaction_info = []
        for reaction in message.reactions:
            # Get emoji name (handle both unicode and custom emojis)
            if isinstance(reaction.emoji, str):
                emoji_name = reaction.emoji  # Unicode emoji
            else:
                emoji_name = f":{reaction.emoji.name}:"  # Custom emoji
            
            # Get list of users who reacted (async, so we'll need to handle this carefully)
            # For now, we'll just show the count and emoji
            reaction_info.append(f"{emoji_name}({reaction.count})")
        
        return f" [Reactions: {', '.join(reaction_info)}]" if reaction_info else ""
    
    async def _get_reaction_users(self, message: discord.Message) -> str:
        """Get detailed reaction information including users"""
        if not message.reactions:
            return ""
        
        reaction_details = []
        try:
            for reaction in message.reactions:
                # Get emoji name
                if isinstance(reaction.emoji, str):
                    emoji_name = reaction.emoji
                else:
                    emoji_name = f":{reaction.emoji.name}:"
                
                # Get users who reacted (limit to avoid spam)
                users = []
                async for user in reaction.users():
                    if len(users) >= 5:  # Limit to first 5 users to avoid spam
                        break
                    if not self._is_user_opted_out(user.id):  # Respect privacy
                        users.append(user.display_name or user.name)
                
                if users:
                    if reaction.count > len(users):
                        user_list = f"{', '.join(users)} and {reaction.count - len(users)} others"
                    else:
                        user_list = ', '.join(users)
                    reaction_details.append(f"{emoji_name}: {user_list}")
                else:
                    reaction_details.append(f"{emoji_name}: {reaction.count} users")
                    
        except Exception as e:
            logger.error(f"Error processing reaction users: {e}")
            return self._process_reactions(message)  # Fallback to simple reaction processing
        
        return f" [Reactions: {' | '.join(reaction_details)}]" if reaction_details else ""
    
    def _create_message_id_map(self, messages: List[discord.Message]) -> Dict[int, int]:
        """Create a mapping from Discord message ID to sequential message ID"""
        message_id_map = {}
        for i, message in enumerate(messages, 1):
            message_id_map[message.id] = i
        return message_id_map
    
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
                    description="Welcome! I can help you summarize Discord conversations using AI, including images, videos, and audio!",
                    color=0x00ff00
                )
                
                embed.add_field(
                    name="What I Do",
                    value=(
                        "I analyze chat messages and create concise summaries of conversations, including:\n"
                        "• Text messages and embeds\n"
                        "• Images (JPG, PNG, GIF, WebP)\n"
                        "• Videos (MP4, MOV, WebM)\n"
                        "• Audio files and voice messages\n"
                        "Use `!help` to see all available commands."
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Privacy Information",
                    value=(
                        "• **No Message Storage**: I do not store user messages, media, or generated summaries\n"
                        "• **External API**: Message data and media are sent to Google's Gemini AI for processing\n"
                        "• **Opt-Out Available**: Use `!optout` to exclude your messages from summaries\n"
                        "• **Opt-In**: Use `!optin` to re-enable summary inclusion"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Legal",
                    value=(
                        "By using channels where this bot is present, you agree to our:\n"
                        "• [Terms of Service](https://dodo-alone.github.io/ShortCord.ai/terms)\n"
                        "• [Privacy Policy](https://dodo-alone.github.io/ShortCord.ai/privacy)\n"
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
    
    async def format_messages_for_ai_interlaced(self, messages: List[discord.Message]) -> List:
        """Format messages for AI processing with media interlaced at the correct positions"""
        if not messages:
            return []
        
        content_parts = []
        prev_time = None
        excluded_count = 0
        media_count = 0
        
        # Create message ID mapping for replies
        message_id_map = self._create_message_id_map(messages)
        
        for message in messages:
            # Skip messages from opted-out users
            if self._is_user_opted_out(message.author.id):
                excluded_count += 1
                continue
            
            # Check for time gaps
            if prev_time and (message.created_at - prev_time).total_seconds() > self.config.get('time_gap_threshold_minutes') * 60:
                content_parts.append("\n--- TIME GAP ---\n")
            
            # Get message details
            display_name = message.author.display_name or message.author.name
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = message.content or "[No text content]"
            message_id = message_id_map[message.id]
            
            # Check for reply
            reply_info = ""
            if message.reference and message.reference.message_id:
                replied_to_id = message_id_map.get(message.reference.message_id)
                if replied_to_id:
                    reply_info = f" [Replying to Message #{replied_to_id}]"
                else:
                    reply_info = " [Replying to message outside conversation]"
            
            # Process embeds
            embed_info = await self._process_embeds(message)
            if embed_info:
                content += " [Embeds: " + " | ".join(embed_info) + "]"
            
            # Process reactions with user details
            reaction_info = await self._get_reaction_users(message)
            
            # Format: Message ID | Display Name | Message Content | Reply Info | Reactions | Timestamp
            message_text = f"Message #{message_id} | {display_name} | {content}{reply_info}{reaction_info} | {timestamp}"
            content_parts.append(message_text)
            
            # Process attachments and add them immediately after the message text with attribution
            if message.attachments:
                for i, attachment in enumerate(message.attachments):
                    # Try to download and process media
                    media_data = await self._download_attachment(attachment)
                    if media_data:
                        data, mime_type = media_data
                        try:
                            # Create a Part for the media and add it with clear attribution
                            media_part = types.Part.from_bytes(data=data, mime_type=mime_type)
                            
                            # Add attribution text before the media
                            media_type = "Image" if mime_type.startswith('image') else \
                                       "Video" if mime_type.startswith('video') else \
                                       "Audio" if mime_type.startswith('audio') else "Media"
                            
                            content_parts.append(f"[{media_type} from Message #{message_id} by {display_name}: {attachment.filename}]")
                            content_parts.append(media_part)
                            media_count += 1
                            logger.info(f"Added attributed media part for {attachment.filename} ({mime_type}) from message #{message_id}")
                        except Exception as e:
                            logger.error(f"Error creating media part for {attachment.filename}: {e}")
                            # Add a note about the failed media with attribution
                            content_parts.append(f"[Media processing failed for Message #{message_id} by {display_name}: {attachment.filename}]")
                    else:
                        # Add a note about unsupported attachment with attribution
                        content_parts.append(f"[Unsupported attachment in Message #{message_id} by {display_name}: {attachment.filename}]")
            
            prev_time = message.created_at
        
        if excluded_count > 0:
            logger.info(f"Excluded {excluded_count} messages from opted-out users")
        
        if media_count > 0:
            logger.info(f"Processed {media_count} attributed media attachments")
        
        return content_parts
    
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
            response_tokens = response.usage_metadata.candidates_token_count # Simple estimation for response
            if response_tokens is None: response_tokens = 0
            self.rate_limiter.record_request(estimated_tokens + response_tokens)
            
            media_count = sum(1 for part in content_parts if isinstance(part, types.Part))
            logger.info(f"Generated summary with ~{estimated_tokens} input tokens and {media_count} interlaced media parts")
            return response_text
            
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
                async for message in ctx.channel.history(limit=count+1):
                    messages.append(message)
                messages = messages[:0:-1]  # Reverse to chronological order
                
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
            
            # Format messages with interlaced media
            content_parts = await bot.format_messages_for_ai_interlaced(messages)
            
            # Check if there are any messages left after filtering opted-out users
            if not content_parts or len(content_parts) <= 1:  # Only the instruction part
                await ctx.send("No messages available to summarize after privacy filtering.")
                return
            
            summary = await bot.generate_summary(content_parts)
            
            # Count media parts for display
            media_count = sum(1 for part in content_parts if isinstance(part, types.Part))
            
            # Split long summaries if needed
            if len(summary) >= 2000:
                # Discord message limit is 2000 characters
                chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        media_note = f" (including {media_count} media files)" if media_count > 0 else ""
                        await ctx.send(f"**Summary of {len(messages)} messages{media_note}:**\n{chunk}")
                    else:
                        await ctx.send(chunk)
            else:
                media_note = f" (including {media_count} media files)" if media_count > 0 else ""
                await ctx.send(f"**Summary of {len(messages)} messages{media_note}:**\n{summary}")
                
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
            description="Your messages and media will no longer be included in summaries.",
            color=0xff9900
        )
        embed.add_field(
            name="What this means:",
            value=(
                "• Your messages won't be sent to Google's AI for processing\n"
                "• Your media attachments won't be analyzed\n"
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
            description="Your messages and media will now be included in summaries again.",
            color=0x00ff00
        )
        embed.add_field(
            name="What this means:",
            value=(
                "• Your messages may be sent to Google's AI for processing\n"
                "• Your media attachments may be analyzed\n"
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
        title="AI Multimodal Summarizer Bot",
        description="Summarize Discord conversations including text, images, videos, and audio using AI",
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
        name="Supported Media Types",
        value=(
            "**Images:** JPG, PNG, GIF, WebP\n"
            "**Videos:** MP4, MOV, WebM, MPEG\n"
            "**Audio:** MP3, WAV, OGG, Discord voice messages\n"
            "**Other:** Embeds and text content"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="Privacy Commands",
        value=(
            "`!optout` - Exclude your messages and media from all summaries\n"
            "`!optin` - Re-include your messages and media in summaries"
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
            "• Messages and media are sent to Google's Gemini AI for processing\n"
            "• No messages, media, or summaries are stored by this bot\n"
            "• Use `!optout` to exclude your content from processing\n"
            "• View our [Terms](https://dodo-alone.github.io/ShortCord.ai/terms) and [Privacy Policy](https://dodo-alone.github.io/ShortCord.ai/privacy)"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="File Limits",
        value=(
            "• Images, Audio: 20MB max\n"
            "• Videos: 100MB max\n"
            "• Rate limiting applies to prevent API overuse"
        ),
        inline=False
    )
    
    help_embed.set_footer(text="Powered by Google Gemini 2.5 Flash AI")
    
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