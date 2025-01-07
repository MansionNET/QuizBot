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
    quiz_game = None
    
    try:
        quiz_game = QuizGame()
        await quiz_game.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal, cleaning up...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        if quiz_game:
            try:
                async with asyncio.timeout(10.0):  # 10 second timeout for cleanup
                    await quiz_game.cleanup()
            except asyncio.TimeoutError:
                logger.error("Cleanup timed out")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True)
        
        # Final cleanup of any remaining tasks
        remaining_tasks = [t for t in asyncio.all_tasks() 
                         if t is not asyncio.current_task()]
        if remaining_tasks:
            logger.warning(f"Found {len(remaining_tasks)} unclosed tasks, "
                         "forcing cleanup...")
            for task in remaining_tasks:
                task.cancel()
            try:
                async with asyncio.timeout(5.0):
                    await asyncio.gather(*remaining_tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                logger.error("Final task cleanup timed out")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Handle Ctrl+C gracefully