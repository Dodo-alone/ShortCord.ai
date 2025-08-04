"""
Text processing utilities
"""

def smart_split_message(text: str, max_length: int = 1900) -> list[str]:
    """
    Split text into chunks while preserving word boundaries and formatting.
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    remaining_text = text
    
    while len(remaining_text) > max_length:
        split_point = find_best_split_point(remaining_text, max_length)
        
        if split_point == -1:
            split_point = max_length
        
        # Extract the chunk and update remaining text
        chunk = remaining_text[:split_point].rstrip()
        chunks.append(chunk)
        remaining_text = remaining_text[split_point:].lstrip()
    
    if remaining_text.strip():
        chunks.append(remaining_text.strip())
    
    return chunks


def find_best_split_point(text: str, max_length: int) -> int:
    """
    Find the best point to split text, prioritizing different break types.
    
    Returns the index where to split, or -1 if no good split point found.
    """
    if len(text) <= max_length:
        return len(text)
    
    # Define split points in order of preference (best to worst)
    split_patterns = [
        '\n\n',
        '. ', 
        '.\n',
        '! ',
        '?\n',
        '? ',
        '!\n',
        '\n',
        '; ',
        ', ',
        ' - ',
        ' ',
    ]
    
    for pattern in split_patterns:
        # Find all occurrences of this pattern within the valid range
        search_text = text[:max_length]
        last_occurrence = search_text.rfind(pattern)
        
        if last_occurrence != -1:
            # Return position after the pattern
            return last_occurrence + len(pattern)
    
    # No good split point found
    return -1