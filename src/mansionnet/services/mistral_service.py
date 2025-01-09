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
    ALTERNATIVE_ANSWERS
)
from ..utils.question_validation import (
    validate_question_content,
    clean_question_text,
    normalize_answer
)

logger = logging.getLogger(__name__)

class MistralService:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment variables")
            
        self.api_key = api_key
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-tiny"
        
        # Simple session setup
        self.session = requests.Session()
        
        # Cache and tracking
        self.question_cache = deque(maxlen=100)
        self.recent_questions = deque(maxlen=20)
        self.recent_categories = deque(maxlen=5)
        
        # Simple rate limiting
        self.last_request_time = None
        self.min_request_interval = 2.0  # Minimum 2 seconds between requests

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
                "temperature": 0.7,
                "max_tokens": 300
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

    async def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a trivia question from Mistral AI."""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                # Select a category that hasn't been used recently
                available_categories = [
                    cat for cat in QUIZ_CATEGORIES.keys()
                    if cat not in self.recent_categories
                ]
                if not available_categories:
                    available_categories = list(QUIZ_CATEGORIES.keys())
                
                category = random.choice(available_categories)
                subcategory = random.choice(QUIZ_CATEGORIES[category])
                difficulty = random.choices(
                    ['easy', 'medium', 'hard'],
                    weights=[0.6, 0.3, 0.1]
                )[0]
                
                # Generate the prompt
                prompt = self._generate_prompt(category, subcategory, difficulty)
                
                # Make API request (synchronously)
                response = self._make_api_request([{
                    "role": "user",
                    "content": prompt
                }])
                
                if not response:
                    attempts += 1
                    continue
                
                # Parse response
                question, answer, fun_fact = self._parse_response(
                    response['choices'][0]['message']['content']
                )
                
                if not all([question, answer, fun_fact]):
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
                
                # Update tracking
                self.recent_questions.append(question)
                self.recent_categories.append(category)
                
                return question, answer, fun_fact
                
            except Exception as e:
                logger.error(f"Error generating question: {e}")
                attempts += 1
        
        # If all attempts fail, return a fallback question that hasn't been used recently
        return self._get_fallback_question()

    def _generate_prompt(self, category: str, subcategory: str, difficulty: str) -> str:
        """Generate a detailed prompt for the Mistral AI API."""
        return f"""Generate a {difficulty} trivia question about {subcategory} 
        (category: {category}) following these STRICT rules:
        
        ESSENTIAL REQUIREMENTS:
        1. Question MUST be about ESTABLISHED, VERIFIED facts only
        2. NO questions about recent or ongoing events
        3. NO questions using words like "first", "only", "most", "best"
        4. Focus on well-documented, mainstream topics
        5. Answer MUST be immediately recognizable
        6. Answer MUST be 1-3 words maximum
        7. NO trick questions or complex wordplay
        8. AVOID specific dates, numbers, or statistics
        9. NO questions about "recent", "latest", or "current" events
        10. Question should have only ONE clear, verifiable answer

        QUESTION STYLE:
        - Simple, clear language
        - Question must be 10-50 characters long
        - Start with "What", "Which", "Who", "Where", or "How"
        - No complex terminology
        - Suitable for casual players
        - Make it interesting and engaging
        
        EXAMPLES OF GOOD QUESTIONS:
        "Which ancient wonder still stands in Egypt?" -> "pyramids"
        "What element makes up most of Earth's atmosphere?" -> "nitrogen"
        "Which band performed 'Bohemian Rhapsody'?" -> "queen"
        "What is the largest planet in our solar system?" -> "jupiter"

        EXAMPLES OF BAD QUESTIONS:
        "Who was the first person to..." (avoid superlatives)
        "Which celebrity recently..." (avoid time-sensitive)
        "What is the most popular..." (avoid rankings)
        "Who is currently leading..." (avoid current events)

        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer in lowercase]
        Fun Fact: [brief, verifiable fact about the answer]"""

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
