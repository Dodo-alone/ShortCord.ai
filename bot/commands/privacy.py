"""
Privacy-related commands (opt-in/opt-out)
"""

import discord
from discord.ext import commands
from core.logger import logger


class PrivacyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='optout')
    async def opt_out(self, ctx):
        """Opt out of message summarization"""
        try:
            success = self.bot.privacy_manager.opt_out_user(ctx.author.id)
            
            if not success:
                await ctx.send("You are already opted out of message summarization.")
                return
            
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
            
        except Exception as e:
            logger.error(f"Error in opt_out command: {e}")
            await ctx.send("An error occurred while processing your opt-out request.")
    
    @commands.command(name='optin')
    async def opt_in(self, ctx):
        """Opt back into message summarization"""
        try:
            success = self.bot.privacy_manager.opt_in_user(ctx.author.id)
            
            if not success:
                await ctx.send("You are not currently opted out of message summarization.")
                return
            
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
            
        except Exception as e:
            logger.error(f"Error in opt_in command: {e}")
            await ctx.send("An error occurred while processing your opt-in request.")


async def setup(bot):
    await bot.add_cog(PrivacyCog(bot))