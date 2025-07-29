#!/usr/bin/env python3

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import and run the bot
if __name__ == "__main__":
    from bot import bot
    
    # Verify required environment variables
    required_vars = ['DISCORD_TOKEN', 'GEMINI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file and ensure all required variables are set.")
        exit(1)
    
    print("Starting Discord AI Summarizer Bot...")
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"Error starting bot: {e}")
        exit(1)