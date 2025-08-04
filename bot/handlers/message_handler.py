"""
Message processing and formatting handler
"""

import discord
import asyncio
from typing import List, Dict
from google.genai import types

from core.config import Config
from core.logger import logger
from bot.utils.cryptography_utils import PrivacyManager
from bot.handlers.media_handler import MediaHandler


class MessageProcessor:
    def __init__(self, privacy_manager: PrivacyManager):
        self.config = Config()
        self.privacy_manager = privacy_manager
        self.media_handler = MediaHandler()
    
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
    
    def _create_message_id_map(self, messages: List[discord.Message]) -> Dict[int, int]:
        """Create a mapping from Discord message ID to sequential message ID"""
        message_id_map = {}
        for i, message in enumerate(messages, 1):
            message_id_map[message.id] = i
        return message_id_map
    
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
                    if not self.privacy_manager.is_user_opted_out(user.id):  # Respect privacy
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
            if self.privacy_manager.is_user_opted_out(message.author.id):
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
                    media_data = await self.media_handler.download_attachment(attachment)
                    if media_data:
                        data, mime_type = media_data
                        try:
                            # Create a Part for the media and add it with clear attribution
                            media_part = types.Part.from_bytes(data=data, mime_type=mime_type)
                            
                            # Add attribution text before the media
                            media_type = self.media_handler.get_media_type_name(mime_type)
                            
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