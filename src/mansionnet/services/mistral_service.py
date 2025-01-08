"""Service for interacting with the Mistral AI API."""
import os
import time
import random
import logging
import requests
import asyncio
from typing import Dict, Tuple, Optional, Set, List
from datetime import datetime, timedelta
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

class RateLimiter:
    """Token bucket rate limiter with request tracking."""
    def __init__(self, rate_limit: int, time_window: int = 60):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.tokens = rate_limit
        self.last_update = datetime.now()
        self.requests = deque(maxlen=rate_limit)
        self.lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire a token. Returns delay needed before making request."""
        async with self.lock:
            now = datetime.now()
            
            # Remove old requests
            while self.requests and (now - self.requests[0]) > timedelta(seconds=self.time_window):
                self.requests.popleft()
            
            # Calculate tokens to restore
            elapsed = (now - self.last_update).total_seconds()
            self.tokens = min(
                self.rate_limit,
                self.tokens + (elapsed * self.rate_limit / self.time_window)
            )
            self.last_update = now

            if self.tokens < 1:
                # Calculate delay needed
                next_token_time = self.requests[0] + timedelta(seconds=self.time_window)
                delay = (next_token_time - now).total_seconds()
                return max(0, delay)

            self.tokens -= 1
            self.requests.append(now)
            return 0

class MistralService:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment variables")
            
        self.api_key = api_key
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-medium"
        
        # Rate limiting settings
        self.rate_limiter = RateLimiter(rate_limit=30)  # 30 requests per minute
        self.base_retry_delay = 1.0
        self.max_retry_delay = 32.0
        self.jitter_factor = 0.1
        
        # Timeouts and retries
        self.request_timeout = 15
        self.operation_timeout = 25
        self.max_retries = 3
        
        # Question management
        self.used_categories: List[str] = []
        self.validation_failures = 0
        self.max_validation_failures = 3
        self.last_category = None
        self.last_subcategory = None
        
        # Session configuration
        self.session = self._setup_session()
        
        # Cache for successful questions
        self.question_cache = deque(maxlen=50)  # Cache last 50 successful questions
        
    def _setup_session(self) -> requests.Session:
        """Configure requests session with proper retry handling."""
        session = requests.Session()
        retry_strategy = requests.adapters.Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            respect_retry_after_header=True
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        return session

    async def _exponential_backoff(self, attempt: int) -> float:
        """Calculate backoff time with jitter."""
        delay = min(
            self.max_retry_delay,
            self.base_retry_delay * (2 ** attempt)
        )
        jitter = delay * self.jitter_factor * random.uniform(-1, 1)
        return delay + jitter

    def _select_category(self) -> Tuple[str, str]:
        # Clear used categories if we've used them all
        if len(self.used_categories) >= len(QUIZ_CATEGORIES):
            self.used_categories.clear()

        available_categories = [
            cat for cat in QUIZ_CATEGORIES.keys()
            if cat not in self.used_categories and cat != self.last_category
        ]
        
        if not available_categories:
            available_categories = list(QUIZ_CATEGORIES.keys())

        category = random.choice(available_categories)
        
        # Avoid same subcategory if possible
        potential_subcategories = [
            sub for sub in QUIZ_CATEGORIES[category]
            if sub != self.last_subcategory
        ]
        
        if not potential_subcategories:
            potential_subcategories = QUIZ_CATEGORIES[category]
            
        subcategory = random.choice(potential_subcategories)
        
        self.used_categories.append(category)
        self.last_category = category
        self.last_subcategory = subcategory
        
        return category, subcategory

    def _generate_prompt(self, category: str, subcategory: str, difficulty: str) -> str:
        return f"""Generate a {difficulty} trivia question about {subcategory} 
        (category: {category}) following these STRICT rules:

        ESSENTIAL REQUIREMENTS:
        1. Question MUST be about SPECIFIC, VERIFIABLE facts
        2. Answer MUST be unique and unambiguous
        3. Question should work internationally
        4. Focus on enduring, well-known topics
        5. No current events or recent developments
        6. Answer must be 1-3 words maximum
        7. Questions should be culturally neutral when possible
        8. Avoid specific dates unless crucial
        9. Questions should be engaging but fair
        10. Include alternative acceptable answers if relevant

        QUESTION STRUCTURE:
        - Clear and concise (under 15 words)
        - Direct question format
        - No complex jargon or technical terms
        - Avoid ambiguous terms
        - Consider multiple valid answers
        - Focus on fundamental knowledge

        DIFFICULTY GUIDELINES:
        - Easy: Common knowledge, everyday facts
        - Medium: Requires specific knowledge but widely known
        - Hard: Detailed knowledge but still fair

        Example format:
        Question: Which element makes up most of Earth's atmosphere?
        Answer: nitrogen
        Alternative Answers: n2
        Fun Fact: Nitrogen makes up about 78% of Earth's atmosphere.
        
        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer]
        Alternative Answers: [other acceptable answers, if any]
        Fun Fact: [interesting, verifiable fact about the answer]"""

    def _get_fallback_question(self) -> Optional[Tuple[str, str, str]]:
        """Get a fallback question when API fails."""
        fallback_questions = [
            (
                "Which element is the most abundant in Earth's atmosphere?",
                "nitrogen",
                "Nitrogen makes up about 78% of Earth's atmosphere."
            ),
            (
                "Which ancient civilization built the pyramids at Giza?",
                "egyptian",
                "The Great Pyramid took around 20 years to build."
            ),
            (
                "Which mountain range separates Europe from Asia?",
                "ural",
                "The Ural Mountains extend about 2,500 km from north to south."
            ),
            (
                "Who painted the Mona Lisa?",
                "da vinci",
                "The Mona Lisa was painted in the early 16th century."
            ),
            (
                "Which instrument has 88 keys?",
                "piano",
                "The modern piano was invented by Bartolomeo Cristofori around 1700."
            ),
            (
                "What is the hardest natural substance?",
                "diamond",
                "Diamonds are formed under high temperature and pressure deep within the Earth."
            ),
            (
                "Which planet is known as the Red Planet?",
                "mars",
                "Mars gets its red color from iron oxide (rust) on its surface."
            )
        ]
        
        # Reset validation failures counter
        self.validation_failures = 0
        
        # Try to get a question from cache first
        if self.question_cache:
            return random.choice(list(self.question_cache))
        
        return random.choice(fallback_questions)

    async def _make_api_request(self, messages: list) -> Optional[Dict]:
        """Make API request with rate limiting and backoff."""
        retries = 0
        
        while retries <= self.max_retries:
            try:
                # Wait for rate limit token
                delay = await self.rate_limiter.acquire()
                if delay > 0:
                    await asyncio.sleep(delay)

                logger.debug(f"Making API request (attempt {retries + 1}/{self.max_retries + 1})")
                
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
                
                async with asyncio.timeout(self.request_timeout):
                    response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.session.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=data,
                            timeout=(3, self.request_timeout - 3)
                        )
                    )
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 0))
                    await asyncio.sleep(max(retry_after, await self._exponential_backoff(retries)))
                    retries += 1
                    continue
                    
                response.raise_for_status()
                return response.json()
                
            except asyncio.TimeoutError:
                logger.warning(f"Request timed out (attempt {retries + 1}/{self.max_retries + 1})")
                await asyncio.sleep(await self._exponential_backoff(retries))
                retries += 1
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if retries < self.max_retries:
                    await asyncio.sleep(await self._exponential_backoff(retries))
                retries += 1
                
            except Exception as e:
                logger.error(f"Unexpected error in API request: {e}")
                break

        logger.error("All API retry attempts failed")
        return None

    def _parse_response(self, content: str) -> Tuple[Optional[str], Optional[str], Set[str], Optional[str]]:
        try:
            # Split by markers
            parts = content.split('\n')
            question = None
            primary_answer = None
            alternative_answers = set()
            fun_fact = None
            
            for part in parts:
                part = part.strip()
                if part.startswith('Question:'):
                    question = clean_question_text(part.split('Question:')[1].strip())
                elif part.startswith('Answer:'):
                    primary_answer = normalize_answer(part.split('Answer:')[1].strip())
                elif part.startswith('Alternative Answers:'):
                    alts = part.split('Alternative Answers:')[1].strip()
                    if alts and alts.lower() != "none":
                        alternative_answers = {
                            normalize_answer(ans.strip())
                            for ans in alts.split(',')
                            if ans.strip()
                        }
                elif part.startswith('Fun Fact:'):
                    fun_fact = part.split('Fun Fact:')[1].strip()
            
            return question, primary_answer, alternative_answers, fun_fact
            
        except Exception as e:
            logger.error(f"Failed to parse API response: {e}")
            return None, None, set(), None

    def _is_valid_question(self, question: str, answer: str, alt_answers: Set[str]) -> bool:
        if not question or not answer:
            return False
            
        question_lower = question.lower()
        answer_lower = answer.lower()

        # Basic validation first
        is_valid, reason = validate_question_content(question, answer)
        if not is_valid:
            logger.debug(f"Question rejected: {reason}")
            return False

        # Check for problematic terms
        if any(term in question_lower for term in VALIDATION_CONFIG['complex_terms']):
            logger.debug("Question rejected: Contains complex terms")
            return False

        if any(term in question_lower for term in VALIDATION_CONFIG['ambiguous_terms']):
            logger.debug("Question rejected: Contains ambiguous terms")
            return False

        # Check answer format
        if len(answer.split()) > 3:
            logger.debug("Answer rejected: Too long")
            return False

        # Add alternative answers if applicable
        if answer_lower in ALTERNATIVE_ANSWERS:
            alt_answers.update(ALTERNATIVE_ANSWERS[answer_lower])

        # Make sure question ends with question mark
        if not question.strip().endswith('?'):
            logger.debug("Question rejected: No question mark")
            return False

        # Check question length against config
        min_length = VALIDATION_CONFIG.get('min_question_length', 20)
        max_length = VALIDATION_CONFIG.get('max_question_length', 200)
        
        if len(question) > max_length:
            logger.debug("Question rejected: Question length outside acceptable range")
            return False

        if len(question) < min_length:
            logger.debug("Question rejected: Question length outside acceptable range")
            return False
            
        # Check for banned characters
        if any(char in question for char in VALIDATION_CONFIG.get('banned_characters', [])):
            logger.debug("Question rejected: Contains banned characters")
            return False
            
        # Reset validation failures counter on success
        self.validation_failures = 0
        return True

    async def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a trivia question with improved caching and fallback."""
        try:
            # Check cache first
            if self.question_cache and random.random() < 0.3:  # 30% chance to use cached question
                cached_question = random.choice(list(self.question_cache))
                if f"{cached_question[0]}:{cached_question[1]}" not in excluded_questions:
                    return cached_question

            async with asyncio.timeout(self.operation_timeout):
                if self.validation_failures >= self.max_validation_failures:
                    logger.warning("Maximum validation failures reached, using fallback")
                    return self._get_fallback_question()

                question_data = await self._get_api_question(excluded_questions)
                if question_data:
                    self.question_cache.append(question_data)
                    return question_data
                    
                return self._get_fallback_question()

        except asyncio.TimeoutError:
            logger.error("Operation timed out while getting trivia question")
            return self._get_fallback_question()
        except Exception as e:
            logger.error(f"Error in get_trivia_question: {e}")
            return self._get_fallback_question()

    async def _get_api_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a question from the API with proper error handling."""
        try:
            category, subcategory = self._select_category()
            difficulty = random.choices(
                ['easy', 'medium', 'hard'],
                weights=[0.6, 0.3, 0.1]
            )[0]
            
            prompt = self._generate_prompt(category, subcategory, difficulty)
            response = await self._make_api_request([{
                "role": "user",
                "content": prompt
            }])
            
            if not response or 'choices' not in response:
                self.validation_failures += 1
                return None
                
            question, answer, alt_answers, fun_fact = self._parse_response(
                response['choices'][0]['message']['content']
            )
            
            if not all([question, answer, fun_fact]):
                self.validation_failures += 1
                return None
                
            if not self._is_valid_question(question, answer, alt_answers):
                self.validation_failures += 1
                return None
                
            question_hash = f"{question}:{answer}"
            if question_hash in excluded_questions:
                return None

            return question, answer, fun_fact
            
        except Exception as e:
            logger.error(f"Error generating API question: {e}")
            self.validation_failures += 1
            return None

    async def close(self):
        """Clean up resources."""
        if self.session:
            await asyncio.get_event_loop().run_in_executor(None, self.session.close)