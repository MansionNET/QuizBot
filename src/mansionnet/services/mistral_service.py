"""Service for interacting with the Mistral AI API."""
import os
import time
import random
import logging
import requests
from typing import Dict, Tuple, Optional, Set, List
from collections import deque
from dotenv import load_dotenv

from ..config.settings import (
    QUIZ_CATEGORIES, 
    VALIDATION_CONFIG,
    ALTERNATIVE_ANSWERS,
    WORLD_REGIONS,
    REGION_WEIGHTS
)
from ..models.database import Database
from ..utils.question_validation import (
    validate_question_content,
    clean_question_text,
    normalize_answer
)

logger = logging.getLogger(__name__)

class MistralService:
    def __init__(self, db: Optional[Database] = None):
        load_dotenv()
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment variables")
            
        self.api_key = api_key
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-medium"  # More reliable model
        
        # Database connection
        self.db = db or Database()
        
        # Simple session setup
        self.session = requests.Session()
        
        # Cache and tracking
        self.question_cache = deque(maxlen=500)  # Increased cache size
        self.recent_questions = deque(maxlen=100)  # Track more questions
        self.recent_categories = deque(maxlen=10)  # Track more categories
        self.recent_answers = deque(maxlen=50)    # Track recent answers
        self.last_category = None                 # Track last used category
        self.consecutive_category_count = 0       # Track category repetition
        
        # Simple rate limiting
        self.last_request_time = None
        self.min_request_interval = 2.0  # Minimum 2 seconds between requests

    async def initialize(self):
        """Initialize the service and database."""
        try:
            await self.db.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Continue even if database init fails

    def _make_api_request(self, messages: list) -> Optional[Dict]:
        """Make a request to the Mistral AI API."""
        try:
            # Simple rate limiting
            if self.last_request_time:
                elapsed = time.time() - self.last_request_time
                if elapsed < self.min_request_interval:
                    time.sleep(self.min_request_interval - elapsed)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.5,  # Lower temperature for more consistent responses
                "max_tokens": 300,
                "top_p": 0.9,  # Add top_p for better response quality
                "presence_penalty": 0.6  # Encourage diverse responses
            }
            
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            self.last_request_time = time.time()
            
            if response.status_code == 429:  # Rate limit
                time.sleep(5)  # Simple backoff
                return None
                
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    def _parse_response(self, content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse the API response into question, answer, and fun fact."""
        try:
            parts = content.split('Question: ')[1].split('Answer:')
            question = clean_question_text(parts[0].strip())
            answer_part = parts[1].split('Fun Fact:')
            answer = normalize_answer(answer_part[0].strip())
            fun_fact = answer_part[1].strip() if len(answer_part) > 1 else None
            
            return question, answer, fun_fact
        except Exception as e:
            logger.error(f"Failed to parse API response: {e}")
            return None, None, None

    def _is_valid_question(self, question: str, answer: str) -> bool:
        """Validate the generated question and answer."""
        is_valid, reason = validate_question_content(question, answer)
        if not is_valid:
            logger.debug(f"Question rejected: {reason}")
            return False
            
        # Check for complex terms
        if any(term in question.lower() for term in VALIDATION_CONFIG['complex_terms']):
            logger.debug("Question rejected: Contains complex terms")
            return False
        
        # Check if question was recently used
        if question in self.recent_questions:
            logger.debug("Question rejected: Recently used")
            return False
        
        return True

    async def _get_next_region(self) -> Tuple[str, str]:
        """Get the next region to focus on based on usage statistics."""
        try:
            least_used = await self.db.get_least_used_categories(limit=5)
            if least_used:
                # Randomly select from least used to add variety
                category_info = random.choice(least_used)
                return category_info['region'], category_info['category']
        except Exception as e:
            logger.debug(f"Failed to get least used categories: {e}")
            # Fall through to default selection
            
        # Default or fallback to weighted random selection
        try:
            region = random.choices(
                list(REGION_WEIGHTS.keys()),
                weights=list(REGION_WEIGHTS.values())
            )[0]
            return region, random.choice(list(QUIZ_CATEGORIES.keys()))
        except Exception as e:
            logger.error(f"Error selecting region: {e}")
            return "Global", next(iter(QUIZ_CATEGORIES.keys()))

    async def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a trivia question from Mistral AI."""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                # Get region and category based on usage statistics
                region, category = await self._get_next_region()
                
                # Get category info with fallback
                try:
                    category_info = QUIZ_CATEGORIES[category]
                    subcategory = random.choice(category_info['subcategories'])
                except (KeyError, IndexError) as e:
                    logger.error(f"Error accessing category info: {e}")
                    attempts += 1
                    continue
                
                # Get regional context if available
                regional_context = None
                try:
                    if category_info.get('regional_context') and category_info.get('regional_examples', {}).get(region):
                        regional_context = category_info['regional_examples'][region]
                except Exception as e:
                    logger.debug(f"Error getting regional context: {e}")
                    # Continue without regional context
                
                # Select difficulty
                difficulty = random.choices(
                    ['easy', 'medium', 'hard'],
                    weights=[0.6, 0.3, 0.1]
                )[0]
                
                # Get recently used answers to avoid repetition
                try:
                    recent_answers_data = await self.db.get_recently_used_answers(days=15)
                    recent_answers = [answer['answer'] for answer in recent_answers_data]
                    self.recent_answers = recent_answers  # Update instance tracking
                except Exception as e:
                    logger.debug(f"Failed to get recent answers: {e}")
                    recent_answers = []
                    recent_answers_data = []
                
                # Generate the prompt with regional context
                prompt = self._generate_prompt(
                    category, 
                    subcategory, 
                    difficulty,
                    region,
                    regional_context,
                    recent_answers
                )
                
                # Make API request and parse response
                response = self._make_api_request([{
                    "role": "user",
                    "content": prompt
                }])
                
                if not response:
                    logger.warning("API request failed or returned empty response")
                    attempts += 1
                    continue
                
                try:
                    content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if not content:
                        logger.warning("Empty content in API response")
                        attempts += 1
                        continue
                        
                    question, answer, fun_fact = self._parse_response(content)
                    if not all([question, answer, fun_fact]):
                        logger.warning("Failed to parse complete question from response")
                        attempts += 1
                        continue
                except (KeyError, IndexError, AttributeError) as e:
                    logger.error(f"Invalid API response structure: {e}")
                    attempts += 1
                    continue
                
                # Validate question
                if not self._is_valid_question(question, answer):
                    attempts += 1
                    continue
                
                # Check if question was already used
                question_hash = f"{question}:{answer}"
                if question_hash in excluded_questions:
                    attempts += 1
                    continue
                
                # Check for category repetition
                if category == self.last_category:
                    self.consecutive_category_count += 1
                    if self.consecutive_category_count > 1:  # Allow max 2 questions from same category
                        attempts += 1
                        continue
                else:
                    self.consecutive_category_count = 0
                    self.last_category = category

                # Check for answer repetition
                if (answer.lower() in self.recent_answers or 
                    answer.lower() in [a.lower() for a in recent_answers] or
                    any(answer.lower() == a['answer'].lower() for a in recent_answers_data)):
                    attempts += 1
                    continue

                # Update tracking
                self.recent_questions.append(question)
                self.recent_categories.append(category)
                self.recent_answers.append(answer.lower())
                
                # Try to add to database, but continue even if it fails
                try:
                    await self.db.add_question_to_history(
                        question=question,
                        answer=answer,
                        category=category,
                        subcategory=subcategory,
                        region=region
                    )
                except Exception as e:
                    logger.error(f"Failed to add question to history: {e}")
                    # Continue even if database update fails
                
                return question, answer, fun_fact
                
            except Exception as e:
                logger.error(f"Error generating question: {e}")
                attempts += 1
        
        # If all attempts fail, return a fallback question that hasn't been used recently
        return self._get_fallback_question()

    def _generate_prompt(
        self, 
        category: str, 
        subcategory: str, 
        difficulty: str,
        region: str,
        regional_context: Optional[str],
        recent_answers: List[str]
    ) -> str:
        """Generate a detailed prompt for the Mistral AI API."""
        # Build regional context string
        region_str = f" focusing on {region}" if region != "Global" else ""
        context_str = f"\nRegional context: {regional_context}" if regional_context else ""
        
        # Build avoided answers string
        avoid_str = ""
        if recent_answers:
            avoid_str = "\nAvoid using these answers that were recently used: " + \
                       ", ".join(recent_answers[:10])  # Limit to 10 for prompt length
        
        # Get current category distribution
        category_counts = {}
        for cat in self.recent_categories:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Find underrepresented categories
        total_questions = len(self.recent_categories) or 1
        category_percentages = {
            cat: (count / total_questions) * 100 
            for cat, count in category_counts.items()
        }

        # Build diversity guidance
        diversity_str = "\nCategory distribution:"
        for cat, pct in category_percentages.items():
            diversity_str += f"\n- {cat}: {pct:.1f}%"
        diversity_str += "\nPrefer categories with lower percentages."

        return f"""Generate a {difficulty} trivia question about {subcategory} 
        (category: {category}){region_str} following these STRICT rules:{context_str}{avoid_str}{diversity_str}
        
        TOPIC REQUIREMENTS:
        1. Questions MUST be diverse across different topics
        2. NO more than two questions from the same category in a row
        3. Balance between:
           - Pop Culture (movies, TV, music, celebrities)
           - Science & Nature (animals, space, environment)
           - History & Geography (world events, places)
           - Sports & Games (rules, teams, players)
           - Arts & Literature (books, paintings, authors)
           - Technology & Internet (apps, websites, gadgets)
           - Food & Drink (cuisine, ingredients, dishes)
           - General Knowledge (common facts, everyday items)

        QUESTION REQUIREMENTS:
        1. Question MUST be about ESTABLISHED, VERIFIED facts only
        2. NO questions about recent or ongoing events
        3. NO questions using words like "first", "only", "most", "best"
        4. Focus on well-documented, MAINSTREAM topics that most people would know
        5. Answer MUST be immediately recognizable to average people
        6. Answer MUST be 1-2 words maximum
        7. NO trick questions or complex wordplay
        8. AVOID specific dates, numbers, or statistics
        9. NO questions about "recent", "latest", or "current" events
        10. Question MUST have only ONE clear, widely known answer
        11. NEVER ask about the same topic twice in a row
        12. NEVER ask variations of the same question
        13. Answers must be COMMON KNOWLEDGE, not obscure facts
        14. NO region-specific questions unless explicitly about that region
        15. Questions should be DIVERSE across different topics

        QUESTION STYLE:
        - Simple, clear language
        - Question must be 10-50 characters long
        - Start with "What", "Which", "Who", "Where", or "How"
        - No complex terminology
        - Suitable for casual players worldwide
        - Make it interesting but keep it simple
        
        EXAMPLES OF GOOD QUESTIONS:
        "Which planet has rings?" -> "saturn"
        "What animal is Mickey Mouse?" -> "mouse"
        "Which metal is used in batteries?" -> "lithium"
        "What is the capital of France?" -> "paris"

        EXAMPLES OF BAD QUESTIONS:
        "Which Native American myth..." (too specific)
        "What is the traditional dance of..." (too regional)
        "Who voiced character X in..." (too obscure)
        "Which organization manages..." (too specialized)

        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer in lowercase]
        Fun Fact: [brief, widely known fact about the answer]"""

    def _get_fallback_question(self) -> Tuple[str, str, str]:
        """Provide a fallback question when API fails."""
        fallback_questions = [
            # Technology
            (
                "What social media app features disappearing photos?",
                "snapchat",
                "Snapchat was originally called 'Picaboo' when it launched."
            ),
            (
                "Which game features players building with colored blocks?",
                "minecraft",
                "Minecraft has sold over 200 million copies worldwide."
            ),
            (
                "What company makes Windows?",
                "microsoft",
                "Windows was first released in 1985."
            ),
            (
                "Which company owns YouTube?",
                "google",
                "Google bought YouTube in 2006 for $1.65 billion."
            ),
            # Entertainment
            (
                "Which streaming service created The Mandalorian?",
                "disney+",
                "The Mandalorian was one of the launch shows for Disney+."
            ),
            (
                "What gaming console competes with Xbox?",
                "playstation",
                "PlayStation was originally developed as a Nintendo partnership."
            ),
            # Science
            (
                "Which planet is closest to the Sun?",
                "mercury",
                "Mercury completes an orbit around the Sun in just 88 Earth days."
            ),
            (
                "What is the hardest natural substance?",
                "diamond",
                "Diamonds are formed deep within the Earth under extreme pressure and heat."
            ),
            # Geography
            (
                "Which desert is the largest in the world?",
                "sahara",
                "The Sahara Desert covers about 31% of Africa."
            ),
            (
                "Which country is home to the Great Barrier Reef?",
                "australia",
                "The Great Barrier Reef is the world's largest coral reef system."
            ),
            # History
            (
                "Which empire built the Colosseum?",
                "roman",
                "The Colosseum could hold up to 50,000-80,000 spectators."
            ),
            (
                "Which civilization built the pyramids at Giza?",
                "egyptian",
                "The Great Pyramid took around 20 years to build."
            ),
            # Music
            (
                "Which band performed 'Bohemian Rhapsody'?",
                "queen",
                "Bohemian Rhapsody took three weeks to record in 1975."
            ),
            (
                "What instrument has 88 keys?",
                "piano",
                "The modern piano was invented by Bartolomeo Cristofori around 1700."
            ),
            # Sports
            (
                "Which sport uses a shuttlecock?",
                "badminton",
                "Badminton is one of the fastest racquet sports."
            ),
            (
                "In which sport would you perform a slam dunk?",
                "basketball",
                "The first slam dunk was performed in the 1940s."
            )
        ]
        
        # Filter out recently used questions
        available_questions = [
            q for q in fallback_questions
            if q[0] not in self.recent_questions
        ]
        
        # If all questions were recently used, reset tracking
        if not available_questions:
            self.recent_questions.clear()
            available_questions = fallback_questions
        
        question = random.choice(available_questions)
        self.recent_questions.append(question[0])
        return question

    async def close(self):
        """Clean up resources."""
        if self.session:
            self.session.close()
        if self.db:
            await self.db.close()
