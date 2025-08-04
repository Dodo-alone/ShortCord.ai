"""
Input validation utilities
"""

from core.config import Config


def validate_message_count(count: int) -> tuple[bool, str]:
    """
    Validate message count for summarization.
    
    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    config = Config()
    
    if count < 5:
        return False, "Message count must be at least 5."
    
    max_limit = config.get('max_messages_limit')
    if count > max_limit:
        return False, f"Maximum message count is {max_limit}."
    
    return True, ""


def validate_config_key(key: str) -> tuple[bool, str]:
    """
    Validate configuration key for security.
    
    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    # Prevent editing of sensitive data via config command
    if key == 'opted_out_users':
        return False, "User opt-out data cannot be modified through the config command for privacy reasons."
    
    return True, ""