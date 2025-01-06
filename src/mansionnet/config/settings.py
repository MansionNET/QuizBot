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
    "Science": [
        "Physics & Space",
        "Biology & Nature",
        "Chemistry",
        "Human Body",
        "Inventions",
        "Environmental Science",
        "Computing & Tech"
    ],
    "History": [
        "Ancient Civilizations",
        "Middle Ages",
        "Renaissance",
        "World Wars",
        "American History",
        "European History",
        "Asian History",
        "African History",
        "Important Discoveries"
    ],
    "Geography": [
        "Countries & Capitals",
        "Mountains & Rivers",
        "Oceans & Seas",
        "Famous Landmarks",
        "Climate & Weather",
        "Natural Wonders",
        "World Cities"
    ],
    "Arts & Culture": [
        "Classical Music",
        "Modern Music",
        "Painting & Sculpture",
        "Literature & Authors",
        "Theater & Dance",
        "Architecture",
        "Museums & Galleries"
    ],
    "Entertainment": [
        "Classic Movies",
        "Modern Films",
        "Television Shows",
        "Video Games",
        "Comics & Animation",
        "Celebrities",
        "Awards & Honors"
    ],
    "Sports": [
        "Olympic Sports",
        "Team Sports",
        "Individual Sports",
        "Sports History",
        "Championships",
        "Notable Athletes",
        "Sports Records"
    ],
    "Language & Literature": [
        "Famous Books",
        "Classic Authors",
        "Poetry",
        "World Languages",
        "Etymology",
        "Literary Characters",
        "Mythology"
    ],
    "STEM": [
        "Mathematics",
        "Computer Science",
        "Engineering",
        "Scientific Method",
        "Famous Scientists",
        "Technology History",
        "Discoveries & Breakthroughs"
    ]
}

# Terms that indicate potentially ambiguous questions
AMBIGUOUS_TERMS = {
    'most', 'best', 'first', 'many', 'several', 'some',
    'few', 'often', 'usually', 'typically', 'recently',
    'current', 'latest', 'modern', 'popular', 'famous'
}

# Complex terms to avoid in questions
COMPLEX_TERMS = {
    'genome', 'algorithm', 'quantum', 'molecular', 'theorem',
    'coefficient', 'synthesis', 'paradigm', 'pursuant',
    'infrastructure', 'implementation', 'methodology',
    'heterogeneous', 'apparatus', 'nomenclature', 'derivative',
    'manifold', 'epistemology', 'optimization', 'polymorphic'
}

# Alternative answers mapping
ALTERNATIVE_ANSWERS = {
    'usa': ['united states', 'america', 'us'],
    'uk': ['united kingdom', 'britain', 'great britain'],
    'earth': ['terra', 'world', 'globe'],
    'sun': ['sol'],
    'moon': ['luna'],
    'automobile': ['car', 'vehicle'],
    'television': ['tv'],
    'mac': ['macintosh', 'apple computer'],
    'pc': ['personal computer', 'desktop computer'],
    'www': ['world wide web', 'web'],
    'phone': ['telephone', 'mobile', 'cellphone'],
    'movie': ['film', 'motion picture'],
    'airplane': ['plane', 'aircraft'],
    'bike': ['bicycle'],
    'internet': ['net', 'cyberspace'],
    'doctor': ['dr', 'physician'],
    'mathematics': ['math', 'maths'],
    'laboratory': ['lab'],
    'photograph': ['photo', 'picture', 'pic'],
    'microphone': ['mic'],
    'application': ['app', 'program'],
    'advertisement': ['ad', 'advert', 'commercial'],
    'representative': ['rep'],
    'professor': ['prof']
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