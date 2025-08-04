"""
Main Discord bot class
"""

import discord
import os
import traceback
from discord.ext import commands
from typing import Set

from core.config import Config
from core.rate_limiter import RateLimiter
from core.logger import logger
from bot.utils.cryptography_utils import PrivacyManager
from bot.handlers.gemini_service import AIService


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
        
        # Initialize core components
        self.config = Config()
        self.rate_limiter = RateLimiter()
        self.privacy_manager = PrivacyManager()
        self.ai_service = AIService()
        
    async def setup_hook(self):
        """Load all command modules"""
        await self.load_extension('bot.commands.summarize')
        await self.load_extension('bot.commands.privacy')
        await self.load_extension('bot.commands.admin')
        await self.load_extension('bot.commands.help')
        logger.info("Loaded all command extensions")
    
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