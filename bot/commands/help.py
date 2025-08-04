"""
Help command
"""

import discord
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='help')
    async def help_command(self, ctx):
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


async def setup(bot):
    await bot.add_cog(HelpCog(bot))