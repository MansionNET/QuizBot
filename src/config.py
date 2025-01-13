import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class BotConfig:
    irc_server: str
    irc_port: int
    irc_nickname: str
    irc_channels: list[str]
    admin_users: list[str]
    mistral_api_key: str
    database_url: str
    question_timeout: int = 30
    min_answer_time: float = 1.0
    base_points: int = 100
    questions_per_game: int = 10
    speed_multiplier_max: float = 2.0

def load_config() -> BotConfig:
    load_dotenv()
    
    return BotConfig(
        irc_server=os.getenv('IRC_SERVER', 'irc.libera.chat'),
        irc_port=int(os.getenv('IRC_PORT', '6667')),
        irc_nickname=os.getenv('IRC_NICKNAME', 'QuizBot'),
        irc_channels=os.getenv('IRC_CHANNELS', '#quizbot').split(','),
        admin_users=os.getenv('ADMIN_USERS', '').split(','),
        mistral_api_key=os.getenv('MISTRAL_API_KEY'),
        database_url=os.getenv('DATABASE_URL', 'sqlite:///quiz.db'),
        question_timeout=int(os.getenv('QUESTION_TIMEOUT', '30')),
        min_answer_time=float(os.getenv('MIN_ANSWER_TIME', '1.0')),
        base_points=int(os.getenv('BASE_POINTS', '100')),
        questions_per_game=int(os.getenv('QUESTIONS_PER_GAME', '10')),
        speed_multiplier_max=float(os.getenv('SPEED_MULTIPLIER_MAX', '2.0'))
    )