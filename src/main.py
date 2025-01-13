#!/usr/bin/env python3
import asyncio
import logging
from dotenv import load_dotenv
import os
import sys

# Add the src directory to Python path
src_path = os.path.dirname(os.path.abspath(__file__))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from models.quiz_state import QuizState
from models.database import Database
from services.irc_service import IRCService
from services.mistral_service import MistralService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize database first
    database = Database(os.getenv('DATABASE_URL', 'sqlite:///quiz.db'))
    await database.connect()
    
    # Initialize services
    mistral_service = MistralService(
        api_key=os.getenv('MISTRAL_API_KEY'),
        database=database,
        min_questions=int(os.getenv('MIN_QUESTIONS', '20'))
    )
    await mistral_service.start()  # Start question generation
    irc_service = IRCService(
        server=os.getenv('IRC_SERVER', 'irc.libera.chat'),
        port=int(os.getenv('IRC_PORT', '6667')),
        nickname=os.getenv('IRC_NICKNAME', 'QuizBot'),
        channels=os.getenv('IRC_CHANNELS', '#quizbot').split(',')
    )
    
    # Initialize quiz state
    quiz_state = QuizState(
        mistral_service=mistral_service,
        database=database,
        irc_service=irc_service,
        admin_users=os.getenv('ADMIN_USERS', '').split(','),
        question_timeout=int(os.getenv('QUESTION_TIMEOUT', '30')),
        questions_per_game=int(os.getenv('QUESTIONS_PER_GAME', '10'))
    )
    
    try:
        await irc_service.connect()
        await quiz_state.start()
        
        # Main event loop
        while True:
            await irc_service.process()
            await asyncio.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down bot...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await quiz_state.cleanup()
        await mistral_service.stop()  # Stop question pool maintenance
        await irc_service.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
