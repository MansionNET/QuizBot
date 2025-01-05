"""Configuration settings for the QuizBot."""
from pathlib import Path
from typing import Dict, List

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# IRC Configuration
IRC_CONFIG = {
    "server": "irc.inthemansion.com",
    "port": 6697,
    "nickname": "QuizBot",
    "channels": ["#quiz", "#test_room"],
    "admin_users": ["Avatar"],
}

# Quiz Configuration
QUIZ_CONFIG = {
    "total_questions": 10,
    "answer_timeout": 30,  # seconds
    "min_answer_length": 1,
    "max_answer_length": 3,  # words
}

# Difficulty Distribution
DIFFICULTY_LEVELS: Dict[str, float] = {
    "easy": 0.6,    # 60% of questions
    "medium": 0.3,  # 30% of questions
    "hard": 0.1     # 10% of questions
}

# Bonus Point Rules
BONUS_RULES = {
    'streak': {3: 1.5, 5: 2.0, 7: 2.5},  # Streak length: bonus multiplier
    'speed': {5: 1.5, 3: 2.0}            # Seconds remaining: bonus multiplier
}

# Database Configuration
DB_CONFIG = {
    "path": BASE_DIR / "data" / "quiz.db",
    "min_connections": 1,
    "max_connections": 10,
}

# Categories for quiz questions
QUIZ_CATEGORIES: Dict[str, List[str]] = {
    "Pop Culture": [
        "Movies & TV", "Music", "Video Games", "Social Media",
        "Celebrities", "Recent Events", "Internet Culture"
    ],
    "Sports & Games": [
        "Football/Soccer", "Basketball", "Olympics", "Popular Athletes",
        "Gaming", "eSports", "Sports History"
    ],
    "Science & Tech": [
        "Everyday Science", "Modern Technology", "Space Exploration",
        "Famous Inventions", "Internet & Apps", "Gadgets"
    ],
    "History & Current Events": [
        "Modern History (1950+)", "Famous People", "Major Events",
        "Recent News", "Popular Movements"
    ],
    "General Knowledge": [
        "Food & Drink", "Countries & Cities", "Famous Landmarks",
        "Popular Brands", "Trending Topics"
    ]
}

# Logging Configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "quizbot.log",
            "formatter": "standard",
            "level": "DEBUG",
        },
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["console", "file"],
            "level": "DEBUG",
        },
    },
}

# Complex terms to avoid in questions
COMPLEX_TERMS = {
    'genome', 'algorithm', 'quantum', 'molecular', 'theorem',
    'coefficient', 'synthesis', 'paradigm', 'pursuant',
    'infrastructure', 'implementation', 'methodology'
}

# IRC Message Formatting
IRC_FORMATTING = {
    "BOLD": "\x02",
    "COLOR": "\x03",
    "RESET": "\x0F",
    "COLORS": {
        "WHITE": "00",
        "BLACK": "01",
        "BLUE": "02",
        "GREEN": "03",
        "RED": "04",
        "BROWN": "05",
        "PURPLE": "06",
        "ORANGE": "07",
        "YELLOW": "08",
        "LIGHT_GREEN": "09",
        "CYAN": "10",
        "LIGHT_CYAN": "11",
        "LIGHT_BLUE": "12",
        "PINK": "13",
        "GREY": "14",
        "LIGHT_GREY": "15"
    }
}