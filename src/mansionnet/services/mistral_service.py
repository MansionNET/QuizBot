"""Service for interacting with the Mistral AI API."""
import os
import time
import random
import logging
import requests
import asyncio
from typing import Dict, Tuple, Optional, Set, List
from dotenv import load_dotenv

from ..config.settings import (
    QUIZ_CATEGORIES, 
    COMPLEX_TERMS, 
    AMBIGUOUS_TERMS,
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
        self.model = "mistral-medium"
        self.used_categories: List[str] = []
        self.last_api_call = 0
        self.min_delay = 1  # Reduced from 2 to 1
        self.request_timeout = 15  # Reduced from 30 to 15
        self.operation_timeout = 25  # Reduced from 45 to 25
        self.max_retries = 2  # Reduced from 3 to 2
        self.fallback_attempt = 0
        self.max_fallback_attempts = 3
        self.validation_failures = 0
        self.max_validation_failures = 3  # Reduced from 5 to 3
        self.last_category = None
        self.last_subcategory = None
        self.session = requests.Session()
        self.session.mount('https://', requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=2,  # Reduced from 3
                backoff_factor=0.5,  # Reduced from 1
                status_forcelist=[429, 500, 502, 503, 504]
            )
        ))

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
        self.fallback_attempt = 0
        
        question = random.choice(fallback_questions)
        return question

    async def _make_api_request(self, messages: list) -> Optional[Dict]:
        """Make API request with timeout and retry handling."""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        if time_since_last_call < self.min_delay:
            await asyncio.sleep(self.min_delay - time_since_last_call + random.uniform(0, 0.5))

        retries = 0
        while retries <= self.max_retries:
            try:
                logger.debug(f"Making API request (attempt {retries + 1}/{self.max_retries + 1})")
                self.last_api_call = time.time()

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
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.session.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=data,
                            timeout=(3, self.request_timeout - 3)  # (connect timeout, read timeout)
                        )
                    )
                
                response.raise_for_status()
                return response.json()
                
            except asyncio.TimeoutError:
                logger.warning(f"Request timed out (attempt {retries + 1}/{self.max_retries + 1})")
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(1 ** retries + random.uniform(0, 0.5))
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(1 ** retries + random.uniform(0, 0.5))
                continue

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
        if any(term in question_lower for term in COMPLEX_TERMS):
            logger.debug("Question rejected: Contains complex terms")
            return False

        if any(term in question_lower for term in AMBIGUOUS_TERMS):
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

        # Additional validation
        if len(question.split()) > 15:
            logger.debug("Question rejected: Too long")
            return False

        if len(question) < 10:
            logger.debug("Question rejected: Too short")
            return False
            
        # Reset validation failures counter on success
        self.validation_failures = 0
        return True

    async def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a trivia question with timeout handling."""
        try:
            async with asyncio.timeout(self.operation_timeout):
                if self.validation_failures >= self.max_validation_failures:
                    logger.warning("Maximum validation failures reached, using fallback")
                    return self._get_fallback_question()

                try:
                    difficulty_weights = {
                        'easy': 0.6,
                        'medium': 0.3,
                        'hard': 0.1
                    }
                    
                    difficulty = random.choices(
                        list(difficulty_weights.keys()),
                        weights=list(difficulty_weights.values())
                    )[0]
                    
                    category, subcategory = self._select_category()
                    prompt = self._generate_prompt(category, subcategory, difficulty)
                    
                    response = await self._make_api_request([{
                        "role": "user",
                        "content": prompt
                    }])
                    
                    if not response or 'choices' not in response:
                        self.validation_failures += 1
                        logger.warning("Failed to get valid response from API")
                        return await self.get_trivia_question(excluded_questions)
                    
                    question, answer, alt_answers, fun_fact = self._parse_response(
                        response['choices'][0]['message']['content']
                    )
                    
                    if not all([question, answer, fun_fact]):
                        self.validation_failures += 1
                        logger.warning("Incomplete question data")
                        return await self.get_trivia_question(excluded_questions)
                    
                    if not self._is_valid_question(question, answer, alt_answers):
                        self.validation_failures += 1
                        return await self.get_trivia_question(excluded_questions)
                    
                    question_hash = f"{question}:{answer}"
                    if question_hash in excluded_questions:
                        logger.debug("Question was recently used")
                        return await self.get_trivia_question(excluded_questions)

                    return question, answer, fun_fact
                        
                except Exception as e:
                    logger.error(f"Error generating question: {e}")
                    self.validation_failures += 1
                    return await self.get_trivia_question(excluded_questions)

        except asyncio.TimeoutError:
            logger.error("Operation timed out while getting trivia question")
            return self._get_fallback_question()
        except Exception as e:
            logger.error(f"Error in get_trivia_question: {e}")
            return self._get_fallback_question()

    async def close(self):
        """Close the session."""
        await asyncio.get_event_loop().run_in_executor(None, self.session.close)