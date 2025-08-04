"""
Entry point for the Discord Summarizer Bot
"""

import os
import traceback
from dotenv import load_dotenv
from bot import SummarizerBot
from core.logger import logger


def main():
    """Main entry point"""
    # Check for required environment variables

    load_dotenv()

    if not os.getenv('DISCORD_TOKEN'):
        logger.error("DISCORD_TOKEN environment variable not set")
        exit(1)
    
    if not os.getenv('GEMINI_API_KEY'):
        logger.error("GEMINI_API_KEY environment variable not set")
        exit(1)
    
    try:
        # Create and run the bot
        bot = SummarizerBot()
        bot.run(os.getenv('DISCORD_TOKEN'))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()