from collections import deque
import time

class RateLimiter:
    """Rate limiter for Gemini API calls"""
    def __init__(self):
        # Gemini 2.5 Flash Lite limits: 15 req/min, 250k tokens/min, 1k req/day
        self.requests_per_minute = deque(maxlen=15)
        self.tokens_per_minute = deque(maxlen=250000)
        self.requests_per_day = deque(maxlen=1000)
        
    async def can_make_request(self, estimated_tokens: int = 1000) -> bool:
        """Check if we can make a request without hitting rate limits"""
        now = time.time()
        
        # Clean old entries
        minute_ago = now - 60
        day_ago = now - 86400
        
        # Remove entries older than 1 minute
        while self.requests_per_minute and self.requests_per_minute[0] < minute_ago:
            self.requests_per_minute.popleft()
        
        # Remove tokens older than 1 minute
        while self.tokens_per_minute and self.tokens_per_minute[0]['time'] < minute_ago:
            self.tokens_per_minute.popleft()
            
        # Remove requests older than 1 day
        while self.requests_per_day and self.requests_per_day[0] < day_ago:
            self.requests_per_day.popleft()
        
        # Check limits
        current_tokens = sum(entry['tokens'] for entry in self.tokens_per_minute)
        
        if (len(self.requests_per_minute) >= 14 or  # Leave buffer
            current_tokens + estimated_tokens > 240000 or  # Leave buffer
            len(self.requests_per_day) >= 950):  # Leave buffer
            return False
            
        return True
    
    def record_request(self, tokens_used: int):
        """Record a successful request"""
        now = time.time()
        self.requests_per_minute.append(now)
        self.tokens_per_minute.append({'time': now, 'tokens': tokens_used})
        self.requests_per_day.append(now)
