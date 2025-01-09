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
    
    # Connection settings
    "connect_timeout": 30,     # seconds
    "reconnect_delay": 5,      # seconds between reconnection attempts
    "max_reconnect_attempts": 3,
    "ping_timeout": 600,       # seconds before connection is considered dead
    
    # Message handling
    "message_timeout": 10,     # seconds for individual message operations
    "message_rate_limit": 1.0, # seconds between messages (anti-flood)
    "buffer_size": 512,        # message buffer size in bytes
    "max_message_queue": 50,   # maximum queued messages
}

# Quiz Configuration
QUIZ_CONFIG = {
    # Game settings
    "total_questions": 10,
    "answer_timeout": 30,     # seconds to answer
    "min_answer_length": 1,
    "max_answer_length": 50,  # characters
    "min_answer_time": 0.1,   # seconds, to prevent automated answers
    "max_used_questions": 1000,  # memory management for question history
    "question_delay": 2,      # seconds between questions
    "max_answer_history": 100,  # number of answers to keep in history
    
    # Player limits
    "max_players_per_game": 50,
    "min_players_to_start": 1,
    "max_concurrent_games": 1,
    
    # Anti-spam settings
    "min_time_between_answers": 0.5,  # seconds
    "max_answers_per_second": 3,
    "answer_cooldown": 1.0,   # seconds after incorrect answer
    "max_consecutive_incorrect": 5,  # before temporary answer ban
    
    # Game variations
    "allow_hints": True,
    "hint_delay": 15,        # seconds after question
    "max_hints": 1,
    "hint_penalty": 0.5,     # score multiplier after hint
    
    # Category weights
    "category_weights": {
        "easy": 0.6,
        "medium": 0.3,
        "hard": 0.1
    }
}

# Bonus Point Rules
BONUS_RULES = {
    'streak': {
        3: 1.5,   # 3 correct answers: 1.5x multiplier
        5: 2.0,   # 5 correct answers: 2.0x multiplier
        7: 2.5    # 7 correct answers: 2.5x multiplier
    },
    'speed': {
        5: 1.5,   # 5+ seconds remaining: 1.5x multiplier
        3: 2.0    # 3+ seconds remaining: 2.0x multiplier
    },
    'difficulty': {
        'easy': 1.0,
        'medium': 1.5,
        'hard': 2.0
    },
    'first_answer': 1.2  # Bonus for first correct answer
}

# Performance and Resource Limits
RESOURCE_LIMITS = {
    "max_memory_mb": 512,
    "max_cpu_percent": 75,
    "gc_threshold": 1000,        # items before garbage collection
    "max_log_size_mb": 100,
    "max_log_age_days": 7,
    "cache_timeout": 3600,       # seconds
    "max_cache_size": 1000,      # items
}

# Database Configuration
DB_CONFIG = {
    "path": BASE_DIR / "data" / "quiz.db",
    "min_connections": 1,
    "max_connections": 10,
    "max_retries": 3,
    "retry_delay": 1,           # seconds
    "operation_timeout": 10,     # seconds
    "connection_timeout": 30,    # seconds
    "idle_timeout": 300,        # seconds
    "max_lifetime": 3600,       # seconds
    "cleanup_interval": 86400,   # 24 hours
    "vacuum_threshold": 1000,    # rows deleted before vacuum
    
    # Query timeouts
    "read_timeout": 5,          # seconds
    "write_timeout": 10,        # seconds
    "long_query_timeout": 30,   # seconds
    
    # Connection pool settings
    "pool_recycle": 3600,       # seconds
    "pool_timeout": 30,         # seconds
    "pool_pre_ping": True,
    
    # Backup settings
    "backup_interval": 86400,    # 24 hours
    "max_backups": 7,
    "backup_timeout": 300       # seconds
}

# Cache Configuration
CACHE_CONFIG = {
    "enabled": True,
    "backend": "memory",        # 'memory' or 'redis'
    "max_size": 1000,          # items
    "ttl": 3600,               # seconds
    "refresh_interval": 300,    # seconds
}

# Question Validation
VALIDATION_CONFIG = {
    # Content validation
    "min_question_length": 10,   # characters
    "max_question_length": 200,  # characters
    "max_answer_words": 3,
    "max_fun_fact_length": 150,  # characters
    
    # Banned characters and patterns
    "banned_characters": ['@', '#', '$', '%', '&', '*'],
    "banned_patterns": [
        r'http[s]?://',
        r'www\.',
        r'\d{4}',              # years
        r'\d+\.\d+\.\d+',      # versions/IPs
    ],
    
    # Terms that indicate potentially ambiguous questions
    "ambiguous_terms": {
        'most', 'best', 'first', 'many', 'several', 'some',
        'few', 'often', 'usually', 'typically', 'recently',
        'current', 'latest', 'modern', 'popular', 'famous'
    },
    
    # Complex terms to avoid in questions
    "complex_terms": {
        'genome', 'algorithm', 'quantum', 'molecular', 'theorem',
        'coefficient', 'synthesis', 'paradigm', 'pursuant',
        'infrastructure', 'implementation', 'methodology',
        'heterogeneous', 'apparatus', 'nomenclature', 'derivative',
        'manifold', 'epistemology', 'optimization', 'polymorphic'
    },
    
    # Content quality thresholds
    "quality_thresholds": {
        "min_unique_words": 5,
        "max_repeated_words": 3,
        "max_consecutive_repeats": 2
    }
}

# Alternative Answer Mappings
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
        "detailed": {
            "format": (
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s "
                "- [%(pathname)s:%(lineno)d]"
            )
        },
    },
    "filters": {
        "require_debug_true": {
            "()": "logging.Filter",
            "name": "debug_only"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "quizbot.log",
            "formatter": "detailed",
            "level": "DEBUG",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "error.log",
            "formatter": "detailed",
            "level": "ERROR",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["console", "file", "error_file"],
            "level": "DEBUG",
        },
        "mansionnet": {  # Application logger
            "handlers": ["console", "file", "error_file"],
            "level": "DEBUG",
            "propagate": False
        }
    },
}

# IRC Message Formatting
IRC_FORMATTING = {
    "BOLD": "\x02",
    "COLOR": "\x03",
    "RESET": "\x0F",
    "ITALIC": "\x1D",
    "UNDERLINE": "\x1F",
    "STRIKETHROUGH": "\x1E",
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

# World Regions for Question Diversity
WORLD_REGIONS = {
    "Africa": [
        "North Africa",
        "West Africa",
        "East Africa",
        "Central Africa",
        "Southern Africa"
    ],
    "Asia": [
        "East Asia",
        "Southeast Asia",
        "South Asia",
        "Central Asia",
        "Middle East"
    ],
    "Europe": [
        "Western Europe",
        "Eastern Europe",
        "Northern Europe",
        "Southern Europe",
        "Central Europe"
    ],
    "Americas": [
        "North America",
        "South America",
        "Central America",
        "Caribbean"
    ],
    "Oceania": [
        "Australia",
        "New Zealand",
        "Pacific Islands"
    ],
    "Global": ["International"]
}

# Regional Distribution Weights
REGION_WEIGHTS = {
    "Africa": 0.15,
    "Asia": 0.2,
    "Europe": 0.2,
    "Americas": 0.2,
    "Oceania": 0.15,
    "Global": 0.1
}

# Quiz Categories with Regional Context
QUIZ_CATEGORIES: Dict[str, Dict[str, List[str]]] = {
    "Science": {
        "subcategories": [
            "Physics & Space",
            "Biology & Nature",
            "Chemistry",
            "Human Body",
            "Inventions",
            "Environmental Science",
            "Computing & Tech"
        ],
        "regional_context": True,  # Can have regional variations
        "regional_examples": {
            "Asia": "Traditional medicine, Asian space programs",
            "Africa": "African botanical discoveries, wildlife",
            "Americas": "NASA, Silicon Valley innovations",
            "Europe": "CERN, European Space Agency",
            "Oceania": "Great Barrier Reef research, Australian wildlife"
        }
    },
    "History": {
        "subcategories": [
            "Ancient Civilizations",
            "Middle Ages",
            "Renaissance",
            "World Wars",
            "Important Discoveries",
            "Cultural Heritage",
            "Trade & Commerce"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Silk Road, Ancient China, Mongol Empire",
            "Africa": "Great Zimbabwe, Egyptian pyramids, Mali Empire",
            "Americas": "Aztec, Inca, Maya civilizations",
            "Europe": "Roman Empire, Medieval period, Renaissance",
            "Oceania": "Aboriginal history, Polynesian navigation"
        }
    },
    "Geography": {
        "subcategories": [
            "Countries & Capitals",
            "Mountains & Rivers",
            "Oceans & Seas",
            "Famous Landmarks",
            "Climate & Weather",
            "Natural Wonders",
            "World Cities"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Himalayas, Yangtze River, Great Wall",
            "Africa": "Sahara Desert, Nile River, Mount Kilimanjaro",
            "Americas": "Amazon River, Rockies, Andes Mountains",
            "Europe": "Alps, Mediterranean Sea, Rhine River",
            "Oceania": "Great Barrier Reef, Uluru, Pacific Islands"
        }
    },
    "Arts & Culture": {
        "subcategories": [
            "Music & Dance",
            "Visual Arts",
            "Literature",
            "Theater",
            "Architecture",
            "Traditional Crafts",
            "Cultural Festivals"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Kabuki theater, Chinese ceramics, Bollywood",
            "Africa": "Tribal art, African drums, storytelling",
            "Americas": "Jazz, Broadway, Native American art",
            "Europe": "Classical music, Renaissance art, Gothic architecture",
            "Oceania": "Aboriginal art, Maori culture, Pacific dance"
        }
    },
    "Entertainment": {
        "subcategories": [
            "Cinema",
            "Television",
            "Video Games",
            "Animation",
            "Popular Music",
            "Digital Media",
            "Entertainment Industry"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "K-pop, anime, Bollywood films",
            "Africa": "Nollywood, African music stars",
            "Americas": "Hollywood, Broadway, Latin music",
            "Europe": "Eurovision, British TV shows",
            "Oceania": "Australian TV, Kiwi films"
        }
    },
    "Sports": {
        "subcategories": [
            "Olympic Sports",
            "Team Sports",
            "Individual Sports",
            "Traditional Games",
            "Championships",
            "Athletes",
            "Sports Culture"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Cricket in India, Table Tennis in China, Sumo",
            "Africa": "African football stars, Marathon runners",
            "Americas": "Baseball, Basketball, American football",
            "Europe": "Football/Soccer, Tennis, Formula 1",
            "Oceania": "Rugby, Australian Rules Football, Surfing"
        }
    },
    "Language & Literature": {
        "subcategories": [
            "World Literature",
            "Poetry & Prose",
            "Languages",
            "Mythology",
            "Folk Tales",
            "Ancient Texts",
            "Modern Writers"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Chinese poetry, Sanskrit literature",
            "Africa": "African storytelling, oral traditions",
            "Americas": "Native American myths, Latin literature",
            "Europe": "Greek mythology, Shakespeare",
            "Oceania": "Aboriginal dreamtime stories, Maori legends"
        }
    },
    "STEM": {
        "subcategories": [
            "Mathematics",
            "Computer Science",
            "Engineering",
            "Scientific Method",
            "Innovation",
            "Technology",
            "Research"
        ],
        "regional_context": True,
        "regional_examples": {
            "Asia": "Asian tech innovation, mathematical discoveries",
            "Africa": "African space programs, tech startups",
            "Americas": "Silicon Valley, NASA achievements",
            "Europe": "CERN, European space missions",
            "Oceania": "Australian scientific research"
        }
    }
}
