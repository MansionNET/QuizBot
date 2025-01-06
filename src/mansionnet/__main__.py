"""Main entry point for the MansionNet QuizBot."""
import logging
import logging.config
import sys
import asyncio
from pathlib import Path

from .core.quiz_game import QuizGame
from .config.settings import LOGGING_CONFIG

def setup_environment():
    """Set up the environment for the bot."""
    # Ensure necessary directories exist
    base_dir = Path(__file__).resolve().parent
    (base_dir / 'data').mkdir(exist_ok=True)
    (base_dir / 'logs').mkdir(exist_ok=True)
    
    # Configure logging
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(__name__)
    
    # Log startup information
    logger.info("Starting MansionNet QuizBot...")
    return logger

async def main():
    """Main function to run the bot."""
    logger = setup_environment()
    
    try:
        quiz_game = QuizGame()
        await quiz_game.run()
    except KeyboardInterrupt:
        logger.info("Shutting down QuizBot...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())