"""
Admin commands
"""

import json
from discord.ext import commands
from core.logger import logger
from bot.utils.validation_utils import validate_config_key


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='config')
    @commands.has_permissions(administrator=True)
    async def config_command(self, ctx, key: str = None, *, value: str = None):
        """Configure bot settings (Admin only)"""
        if key is not None:
            # Validate config key
            is_valid, error_msg = validate_config_key(key)
            if not is_valid:
                await ctx.send(error_msg)
                return
        
        if key is None:
            # Show current config (excluding sensitive data)
            config_copy = self.bot.config.config.copy()
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
                count = self.bot.privacy_manager.get_opted_out_count()
                await ctx.send(f"**{key}:** [{count} opted-out users] (hashed data not shown)")
                return
            
            current_value = self.bot.config.get(key)
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

            if self.bot.config.get(key) is None:
                await ctx.send(f"There is no setting {key}")
                return
            
            self.bot.config.set(key, parsed_value)
            await ctx.send(f"Configuration updated: **{key}** = {parsed_value}")
            logger.info(f"Config updated by {ctx.author}: {key} = {parsed_value}")
            
        except Exception as e:
            await ctx.send(f"Error updating configuration: {e}")
    
    @config_command.error
    async def config_error(self, ctx, error):
        """Error handler for config command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))