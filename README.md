# Discord AI Text Summarizer Bot

A Discord bot that uses Google Gemini AI to summarize chat conversations with intelligent rate limiting and configurable prompts.

## Features

- **Smart Summarization**: Uses Google Gemini 2.0 Flash Exp to create concise summaries
- **Flexible Commands**: Summarize since last activity or specify message count
- **Rate Limiting**: Built-in protection against API limits (15 req/min, 250k tokens/min, 1k req/day)
- **Time Gap Detection**: Identifies conversation breaks and treats them appropriately
- **Rich Presence**: Shows helpful status and typing indicators
- **Configurable**: Admin-configurable system prompts and settings
- **Comprehensive Logging**: Tracks errors, rate limits, and bot activity
- **Security**: No logging of user messages or AI outputs

## Setup

### 1. Prerequisites
- Python 3.8+
- Discord Application with Bot Token
- Google Gemini API Key (free tier)

### 2. Installation

```bash
# Clone or download the project files
git clone
cd discord-summarizer-bot

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 3. Configuration

Edit `.env` file with your tokens:
```env
DISCORD_TOKEN=your_discord_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

#### Getting Discord Bot Token:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application
3. Go to "Bot" section
4. Click "Reset Token" and copy the token
5. Enable "Message Content Intent" under Privileged Gateway Intents

#### Getting Gemini API Key:
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API key
3. Copy the key

### 4. Running the Bot

```bash
python bot.py
```

## Commands

- `!summarize` - Summarize messages since you were last active
- `!summarize <count>` - Summarize the last `<count>` messages (max 200)
- `!help` - Show help information

### Admin Commands (Administrator permission required)
- `!config` - View current configuration
- `!config <key>` - View specific configuration value
- `!config <key> <value>` - Set configuration value

## Configuration Options

The bot creates a `config.json` file with these settings:

- `system_prompt`: Instructions for the AI summarizer
- `max_messages_default`: Default message limit for auto-detection
- `max_messages_limit`: Maximum messages allowed per request
- `time_gap_threshold_minutes`: Minutes to detect conversation breaks

## Rate Limiting

The bot implements comprehensive rate limiting for Gemini 2.0 Flash Exp:
- **15 requests per minute** (with 1 request buffer)
- **250,000 tokens per minute** (with 10k token buffer)
- **1,000 requests per day** (with 50 request buffer)

## Input Format

Messages are formatted for AI processing as:
```
Display Name | Message Content | 2024-01-01 12:00:00 UTC
Display Name | Another message | 2024-01-01 12:01:00 UTC

--- TIME GAP ---

Display Name | Message after break | 2024-01-01 13:00:00 UTC
```

## Security & Privacy Considerations

### ✅ Security Features
- No storage of user messages or AI responses
- Proper error handling and logging
- Rate limiting prevents API abuse
- Admin-only configuration commands
- Environment variable protection for secrets

### ⚠️ Privacy Considerations
- **Message Access**: Bot can read all messages in channels it's added to
- **API Transmission**: Messages are sent to Google's Gemini API for processing

### 🔒 Recommendations
- Only add bot to channels where summarization is needed
- Review Google's [Gemini API Privacy Policy](https://ai.google.dev/terms)
- Consider channel permissions carefully
- Inform users that their messages may be summarized
- Regularly rotate API keys

## Logging

The bot logs to both console and `bot.log` file:
- Connection events
- Command usage
- Rate limit hits
- Errors and exceptions
- Configuration changes

**Note**: User messages and AI outputs are NOT logged for privacy.

## Token Limits

- **Input limit**: 1,048,576 tokens (~4.2M characters)
- **Output limit**: 65,536 tokens (~262k characters)
- Automatic truncation if messages exceed input limit

## Troubleshooting

### Common Issues

1. **"Rate limit reached"**
   - Wait a few minutes before trying again
   - Reduce message count if using `!summarize <count>`

2. **"Message history too long"**
   - Use `!summarize` with a smaller number
   - Check if there are large messages or attachments

3. **Bot not responding**
   - Check bot permissions in Discord
   - Verify tokens in `.env` file
   - Check `bot.log` for errors

4. **"Missing Permissions" for config**
   - Ensure you have Administrator role in Discord server

### Log Files
- Check `bot.log` for detailed error information
- Logs rotate automatically to prevent disk space issues

### Contributing
1. Fork the repository
2. Create feature branch
3. Make changes with proper error handling
4. Test thoroughly
5. Submit pull request

## License

This project is provided as-is for educational and personal use. Review Google's Gemini API terms and Discord's API terms before commercial use.
