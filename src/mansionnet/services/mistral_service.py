"""Service for interacting with the Mistral AI API."""
import os
import time
import random
import logging
import requests
from typing import Dict, Tuple, Optional, Set
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
        self.used_categories = set()
        self.last_api_call = 0
        self.min_delay = 2
        self.timeout = 20
        self.max_retries = 2
        self.fallback_attempt = 0
        self.max_fallback_attempts = 3

    def _select_category(self) -> Tuple[str, str]:
        if len(self.used_categories) >= len(QUIZ_CATEGORIES):
            self.used_categories.clear()

        available_categories = [
            cat for cat in QUIZ_CATEGORIES.keys()
            if cat not in self.used_categories
        ]
        
        if not available_categories:
            available_categories = list(QUIZ_CATEGORIES.keys())

        category = random.choice(available_categories)
        subcategory = random.choice(QUIZ_CATEGORIES[category])
        
        self.used_categories.add(category)
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
        - Avoid ambiguous words ({', '.join(list(AMBIGUOUS_TERMS)[:5])})
        - Consider multiple valid answers
        - Focus on fundamental knowledge

        DIFFICULTY GUIDELINES:
        - Easy: Common knowledge, everyday facts
        - Medium: Requires specific knowledge but widely known
        - Hard: Detailed knowledge but still fair

        Example by category:
        - Science: "Which element makes up most of Earth's atmosphere?" -> "nitrogen"
        - History: "Which empire built the pyramids at Giza?" -> "egyptian"
        - Geography: "Which mountain range separates Europe from Asia?" -> "ural"
        - Arts: "Who painted the Mona Lisa?" -> "da vinci"
        
        BAD EXAMPLES:
        - "Who was the first person to..." (avoid superlatives)
        - "Which recent movie..." (avoid time-sensitive)
        - "What is the most popular..." (avoid subjective)
        - "Who is currently..." (avoid current events)

        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer]
        Alternative Answers: [other acceptable answers, if any]
        Fun Fact: [interesting, verifiable fact about the answer]"""

    def _make_api_request(self, messages: list) -> Optional[Dict]:
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        if time_since_last_call < self.min_delay:
            time.sleep(self.min_delay - time_since_last_call)

        retries = 0
        while retries <= self.max_retries:
            try:
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
                
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(f"API timeout (attempt {retries + 1}/{self.max_retries + 1})")
                retries += 1
                if retries <= self.max_retries:
                    time.sleep(2 * retries)
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {e}")
                return None

        logger.error("All API retry attempts failed")
        return None

    def _parse_response(self, content: str) -> Tuple[Optional[str], Optional[str], Set[str], Optional[str]]:
        try:
            parts = content.split('Question: ')[1].split('Answer:')
            question = clean_question_text(parts[0].strip())
            
            remaining = parts[1].split('Alternative Answers:')
            primary_answer = normalize_answer(remaining[0].strip())
            
            alt_and_fact = remaining[1].split('Fun Fact:')
            alternative_answers = {
                normalize_answer(ans.strip())
                for ans in alt_and_fact[0].strip().split(',')
                if ans.strip()
            }
            
            fun_fact = alt_and_fact[1].strip()
            
            return question, primary_answer, alternative_answers, fun_fact
            
        except (IndexError, AttributeError) as e:
            logger.error(f"Failed to parse API response: {e}")
            return None, None, set(), None

    def _is_valid_question(self, question: str, answer: str, alt_answers: Set[str]) -> bool:
        is_valid, reason = validate_question_content(question, answer)
        if not is_valid:
            logger.debug(f"Question rejected: {reason}")
            return False

        if any(term in question.lower() for term in COMPLEX_TERMS):
            logger.debug("Question rejected: Contains complex terms")
            return False

        if any(term in question.lower() for term in AMBIGUOUS_TERMS):
            logger.debug("Question rejected: Contains ambiguous terms")
            return False

        if len(answer.split()) > 3:
            logger.debug("Answer rejected: Too long")
            return False

        if answer in ALTERNATIVE_ANSWERS:
            alt_answers.update(ALTERNATIVE_ANSWERS[answer])

        return True

    def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        attempts = 0
        max_attempts = 3
        
        while attempts < max_attempts:
            try:
                category, subcategory = self._select_category()
                
                difficulty = random.choices(
                    ['easy', 'medium', 'hard'],
                    weights=[0.6, 0.3, 0.1]
                )[0]
                
                prompt = self._generate_prompt(category, subcategory, difficulty)
                
                response = self._make_api_request([{
                    "role": "user",
                    "content": prompt
                }])
                
                if not response:
                    logger.warning(f"Failed to get response from API (attempt {attempts + 1}/{max_attempts})")
                    attempts += 1
                    continue
                
                question, answer, alt_answers, fun_fact = self._parse_response(
                    response['choices'][0]['message']['content']
                )
                
                if not all([question, answer, fun_fact]):
                    attempts += 1
                    continue
                
                if not self._is_valid_question(question, answer, alt_answers):
                    attempts += 1
                    continue
                
                question_hash = f"{question}:{answer}"
                if question_hash in excluded_questions:
                    attempts += 1
                    continue

                return question, answer, fun_fact
                
            except Exception as e:
                logger.error(f"Error generating question: {e}")
                attempts += 1
        
        # Try to get a fallback question, with its own retry counter
        self.fallback_attempt += 1
        if self.fallback_attempt >= self.max_fallback_attempts:
            logger.error("Maximum fallback attempts reached")
            return None
            
        logger.info(f"Using fallback question (attempt {self.fallback_attempt})")
        fallback = self._get_fallback_question()
        
        # Verify fallback question isn't in excluded set
        question_hash = f"{fallback[0]}:{fallback[1]}"
        if question_hash in excluded_questions:
            return self.get_trivia_question(excluded_questions)
            
        return fallback

    def _get_fallback_question(self) -> Tuple[str, str, str]:
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
                "Which playwright wrote Romeo and Juliet?",
                "shakespeare",
                "Romeo and Juliet was written between 1591 and 1595."
            ),
            (
                "What force pulls objects toward Earth?",
                "gravity",
                "Gravity was first described mathematically by Isaac Newton."
            ),
            (
                "Which gas do plants absorb from the air?",
                "carbon dioxide",
                "Plants convert carbon dioxide into oxygen through photosynthesis."
            ),
            (
                "Which planet is known as the Red Planet?",
                "mars",
                "Mars gets its red color from iron oxide (rust) on its surface."
            ),
            (
                "What organ pumps blood through the body?",
                "heart",
                "The average heart beats over 100,000 times per day."
            ),
            (
                "How many players are on a soccer team during a match?",
                "eleven",
                "The rules establishing 11 players were set in 1897."
            ),
            (
                "Which scientist is known for discovering electricity?",
                "franklin",
                "Benjamin Franklin conducted his famous kite experiment in 1752."
            ),
            (
                "What is the name for a three-sided shape?",
                "triangle",
                "A triangle's three angles always add up to 180 degrees."
            ),
            (
                "Which galaxy contains our solar system?",
                "milky way",
                "The Milky Way contains over 100 billion stars."
            ),
            (
                "Which big cat has black stripes?",
                "tiger",
                "Each tiger's stripe pattern is unique, like human fingerprints."
            )
        ]
        
        return random.choice(fallback_questions)