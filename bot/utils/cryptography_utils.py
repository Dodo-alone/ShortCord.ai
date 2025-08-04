"""
Privacy utilities for user opt-out/opt-in functionality
"""

import os
import hashlib
import secrets
import traceback
from typing import Set
from core.config import Config
from core.logger import logger


class PrivacyManager:
    def __init__(self):
        self.config = Config()
        self.salt = self._load_or_create_salt()
        self.opted_out_users: Set[str] = set()
        self._load_opted_out_users()
    
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
    
    def is_user_opted_out(self, user_id: int) -> bool:
        """Check if a user has opted out"""
        hashed_id = self._hash_user_id(user_id)
        return hashed_id in self.opted_out_users
    
    def opt_out_user(self, user_id: int) -> bool:
        """Opt out a user. Returns True if successfully opted out, False if already opted out"""
        hashed_id = self._hash_user_id(user_id)
        
        if hashed_id in self.opted_out_users:
            return False
        
        self.opted_out_users.add(hashed_id)
        self._save_opted_out_users()
        logger.info(f"User opted out of summarization")
        return True
    
    def opt_in_user(self, user_id: int) -> bool:
        """Opt in a user. Returns True if successfully opted in, False if already opted in"""
        hashed_id = self._hash_user_id(user_id)
        
        if hashed_id not in self.opted_out_users:
            return False
        
        self.opted_out_users.remove(hashed_id)
        self._save_opted_out_users()
        logger.info(f"User opted back into summarization")
        return True
    
    def get_opted_out_count(self) -> int:
        """Get the number of opted-out users"""
        return len(self.opted_out_users)