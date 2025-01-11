"""Service for interacting with the Mistral AI API with enhanced validation and tracking."""
import os
import re
import time
import json
import random
import logging
from typing import Dict, Tuple, Optional, List, Set, Any
import requests
from collections import deque, defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

from ..models.database import Database
from ..config.settings import QUIZ_CATEGORIES

logger = logging.getLogger(__name__)

# Fallback questions for reliability
FALLBACK_QUESTIONS = [
    # Science & Nature
    (
        "What force pulls objects towards Earth?",
        "gravity",
        "Gravity is one of the four fundamental forces of nature and keeps planets in orbit."
    ),
    (
        "Which gas do plants absorb from the air?",
        "carbon dioxide",
        "Plants convert carbon dioxide into oxygen through photosynthesis."
    ),
    (
        "What is Earth's largest ocean?",
        "pacific",
        "The Pacific Ocean covers more area than all Earth's continents combined."
    ),
    (
        "What organ filters blood in the human body?",
        "kidneys",
        "The kidneys filter about 120-150 quarts of blood every day."
    ),
    (
        "Which planet is known as the Red Planet?",
        "mars",
        "Mars gets its red color from iron oxide (rust) on its surface."
    ),
    # Geography
    (
        "Which desert is the largest hot desert?",
        "sahara",
        "The Sahara covers about 3.6 million square miles in North Africa."
    ),
    (
        "What is the deepest ocean?",
        "pacific",
        "The Pacific Ocean contains the deepest known point, the Mariana Trench."
    ),
    (
        "Which mountain range crosses the equator?",
        "andes",
        "The Andes Mountains run through seven countries in South America."
    ),
    # Basic Knowledge
    (
        "How many sides does a triangle have?",
        "three",
        "A triangle is the simplest polygon and has three angles that sum to 180 degrees."
    ),
    (
        "What molecule do plants produce in photosynthesis?",
        "oxygen",
        "Plants produce oxygen as a byproduct of converting sunlight into energy."
    )
]

# Fact validation for geography questions
GEOGRAPHY_FACTS = {
    'landlocked_countries': {
        'afghanistan', 'austria', 'bhutan', 'bolivia', 'botswana', 'burkina faso',
        'burundi', 'chad', 'czech republic', 'ethiopia', 'hungary', 'kazakhstan',
        'laos', 'malawi', 'mali', 'mongolia', 'nepal', 'niger', 'paraguay',
        'rwanda', 'slovakia', 'switzerland', 'uganda', 'zambia', 'zimbabwe'
    },
    'largest_bodies': {
        'ocean': 'pacific',
        'sea': 'caribbean',
        'gulf': 'mexico',
        'lake_salt': 'caspian',
        'lake_fresh': 'superior'
    },
    'rivers': {
        'longest': 'nile',
        'widest': 'amazon'
    },
    'mountains': {
        'highest': 'everest',
        'africa': 'kilimanjaro',
        'europe': 'mont blanc',
        'south_america': 'aconcagua'
    }
}

class MistralService:
    """Service for generating and validating trivia questions."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize the service with enhanced tracking."""
        load_dotenv()
        self.api_key = os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY not found")
            
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-medium"
        self.db = db or Database()
        
        # Question tracking
        self.recent_questions = deque(maxlen=100)
        self.used_answers = deque(maxlen=100)
        self.recent_categories = deque(maxlen=5)
        self.category_counts = defaultdict(int)
        
        # Rate limiting
        self.last_request_time = None
        self.min_request_interval = 2.0

    async def initialize(self):
        """Initialize database connection and tracking."""
        await self.db.initialize()
        
        # Load recent questions from database
        try:
            recent = await self.db.execute_query("""
                SELECT question, answer 
                FROM question_history 
                WHERE last_asked > datetime('now', '-7 days')
                ORDER BY last_asked DESC
            """)
            
            # Initialize tracking deques
            self.recent_questions.extend(q[0] for q in recent)
            self.used_answers.extend(q[1] for q in recent)
            
        except Exception as e:
            logger.error(f"Failed to load recent questions: {e}")

    def _validate_question(self, question: str, answer: str, category: str) -> bool:
        """Validate question content and structure."""
        # Basic validation
        if not (10 <= len(question) <= 200 and 2 <= len(answer) <= 30):
            return False
            
        if not question.endswith('?'):
            return False
            
        # Structure validation
        q_lower = question.lower()
        if not any(q_lower.startswith(w) for w in ['what', 'which', 'who', 'where', 'how']):
            return False
            
        # Content validation
        banned_patterns = [
            r'(19|20)\d{2}',          # Years
            r'recent|current|latest',  # Time-sensitive
            r'most|best|worst',       # Subjective
            r'popular|famous|well known',  # Popularity-based
            r'(american|british|european)',  # Region-specific
            r'several|many|few'       # Ambiguous
        ]
        
        if any(re.search(pattern, q_lower) for pattern in banned_patterns):
            return False
            
        # Category-specific validation
        if category == 'Geography':
            return self._validate_geography(question, answer)
            
        return True

    def _validate_geography(self, question: str, answer: str) -> bool:
        """Validate geography-specific questions."""
        q_lower = question.lower()
        a_lower = answer.lower()
        
        # Landlocked country validation
        if 'landlocked' in q_lower:
            return a_lower in GEOGRAPHY_FACTS['landlocked_countries']
            
        # Bodies of water validation
        if 'largest' in q_lower:
            for body_type, largest in GEOGRAPHY_FACTS['largest_bodies'].items():
                if body_type.replace('_', ' ') in q_lower:
                    return a_lower == largest
                    
        # River validation
        if 'river' in q_lower:
            if 'longest' in q_lower:
                return a_lower == GEOGRAPHY_FACTS['rivers']['longest']
            if 'widest' in q_lower:
                return a_lower == GEOGRAPHY_FACTS['rivers']['widest']
                
        # Mountain validation
        if 'mountain' in q_lower and 'highest' in q_lower:
            for region, peak in GEOGRAPHY_FACTS['mountains'].items():
                if region in q_lower:
                    return a_lower == peak
                    
        return True

    def _make_api_request(self, messages: list) -> Optional[Dict]:
        """Make request to Mistral API with rate limiting."""
        try:
            # Rate limiting
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
                "max_tokens": 300,
                "top_p": 0.9,
                "presence_penalty": 0.6,
                "frequency_penalty": 0.3
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            self.last_request_time = time.time()
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    def _generate_prompt(self, category: str) -> str:
        """Generate API prompt for question generation."""
        return f"""Generate a globally relevant trivia question about {category} following these rules:

1. Make it factually accurate and verifiable
2. Use simple, clear language
3. Focus on universal, timeless knowledge
4. Avoid dates, current events, and region-specific content
5. Make it challenging but fair

Requirements:
- Start with What, Which, Who, Where, or How
- Answer must be 1-3 words
- No complex terminology
- No current events or dates
- No region-specific content
- No ambiguous terms (most, best, etc.)

Format response EXACTLY as:
Question: [your question]
Answer: [answer in lowercase]
Fun Fact: [interesting fact about the answer]

Example questions:
- "What force pulls objects towards Earth?" -> "gravity"
- "Which gas do plants use in photosynthesis?" -> "carbon dioxide"
- "What is the deepest ocean?" -> "pacific"
"""

    def _parse_response(self, content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse API response with validation."""
        try:
            # Split response parts
            parts = content.split('Question: ')
            if len(parts) != 2:
                return None, None, None
                
            question_parts = parts[1].split('Answer:')
            if len(question_parts) != 2:
                return None, None, None
                
            question = question_parts[0].strip()
            
            answer_parts = question_parts[1].split('Fun Fact:')
            if len(answer_parts) != 2:
                return None, None, None
                
            answer = answer_parts[0].strip().lower()
            fun_fact = answer_parts[1].strip()
            
            # Validate components
            if not self._validate_components(question, answer, fun_fact):
                return None, None, None
                
            return question, answer, fun_fact
            
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return None, None, None

    def _validate_components(self, question: str, answer: str, fun_fact: str) -> bool:
        """Validate parsed response components."""
        # Length validation
        if not (10 <= len(question) <= 200):
            return False
        if not (2 <= len(answer) <= 30):
            return False
        if not (20 <= len(fun_fact) <= 200):
            return False
            
        # Format validation
        if not question.endswith('?'):
            return False
        if len(answer.split()) > 3:
            return False
        if not fun_fact[0].isupper() or not fun_fact.endswith('.'):
            return False
            
        return True

    def _get_fallback_question(self) -> Tuple[str, str, str]:
        """Get a fallback question with tracking."""
        # Filter out recently used questions
        available = [
            q for q in FALLBACK_QUESTIONS
            if q[0] not in self.recent_questions and 
            q[1] not in self.used_answers
        ]
        
        # Reset tracking if all questions used
        if not available:
            self.recent_questions.clear()
            self.used_answers.clear()
            available = FALLBACK_QUESTIONS
        
        # Select and track question
        question = random.choice(available)
        self.recent_questions.append(question[0])
        self.used_answers.append(question[1])
        
        return question

    async def get_trivia_question(self, excluded_questions: Optional[Set[str]] = None) -> Optional[Tuple[str, str, str]]:
        """Get a balanced trivia question with validation."""
        excluded_questions = excluded_questions or set()
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                # Select category with balance
                available_categories = [
                    cat for cat in QUIZ_CATEGORIES.keys()
                    if cat not in self.recent_categories
                ]
                
                if not available_categories:
                    available_categories = list(QUIZ_CATEGORIES.keys())
                
                category = random.choice(available_categories)
                subcategory = random.choice(QUIZ_CATEGORIES[category]['subcategories'])
                
                # Generate question
                prompt = self._generate_prompt(category)
                response = self._make_api_request([{
                    "role": "user",
                    "content": prompt
                }])
                
                if not response:
                    continue
                    
                content = response['choices'][0]['message']['content']
                question, answer, fun_fact = self._parse_response(content)
                
                if not all([question, answer, fun_fact]):
                    continue
                    
                # Validate question
                if not self._validate_question(question, answer, category):
                    continue
                    
                # Check for duplicates
                question_hash = f"{question}:{answer}"
                if question_hash in excluded_questions:
                    continue
                    
                # Update tracking
                self.recent_questions.append(question)
                self.used_answers.append(answer)
                self.recent_categories.append(category)
                self.category_counts[category] += 1
                
                # Store in database
                try:
                    await self.db.add_question_to_history(
                        question=question,
                        answer=answer,
                        category=category,
                        subcategory=subcategory,
                        region='Global',
                        difficulty='medium'
                    )
                except Exception as e:
                    logger.error(f"Failed to store question in database: {e}")
                
                return question, answer, fun_fact
                
            except Exception as e:
                logger.error(f"Error generating question (attempt {attempt + 1}): {e}")
                continue
        
        # Use fallback if all attempts fail
        logger.warning("Failed to generate valid question, using fallback")
        return self._get_fallback_question()

    async def close(self):
        """Clean up resources."""
        if self.db:
            await self.db.close()