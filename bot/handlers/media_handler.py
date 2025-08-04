"""
Media download and processing handler
"""

import discord
import aiohttp
from typing import Optional, Tuple, Set
from core.logger import logger


class MediaHandler:
    def __init__(self):
        # Supported media types
        self.supported_image_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
        self.supported_video_types = {'video/mp4', 'video/mpeg', 'video/quicktime', 'video/webm'}
        self.supported_audio_types = {'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/webm'}
        
        # File size limits (in bytes)
        self.max_file_size = 20 * 1024 * 1024  # 20MB general limit
        self.max_video_size = 100 * 1024 * 1024  # 100MB for video
    
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
    
    async def download_attachment(self, attachment: discord.Attachment) -> Optional[Tuple[bytes, str]]:
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
    
    def get_media_type_name(self, mime_type: str) -> str:
        """Get human-readable media type name"""
        if mime_type.startswith('image'):
            return "Image"
        elif mime_type.startswith('video'):
            return "Video"
        elif mime_type.startswith('audio'):
            return "Audio"
        else:
            return "Media"