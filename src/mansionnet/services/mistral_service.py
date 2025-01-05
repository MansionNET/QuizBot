"""Service for interacting with the Mistral AI API."""
import os
from typing import Dict, Tuple, Optional
import logging
import requests
import random
from dotenv import load_dotenv

from ..config.settings import QUIZ_CATEGORIES, COMPLEX_TERMS
from ..utils.question_validation import (
    validate_question_content,
    clean_question_text,
    normalize_answer
)

logger = logging.getLogger(__name__)

class MistralService:
    """Handles all interactions with the Mistral AI API."""

    def __init__(self):
        """Initialize the Mistral AI service."""
        load_dotenv()
        self.api_key = self._load_api_key()
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-tiny"

    def _load_api_key(self) -> str:
        """Load the Mistral AI API key from environment variables."""
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment variables")
        return api_key

    def _generate_prompt(self, category: str, subcategory: str, 
                        difficulty: str) -> str:
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
        - Under 15 words
        - No complex terminology
        - Focused on popular culture, technology, sports, history, science, movies and entertainment
        - Suitable for casual players and some expert
        
        EXAMPLES OF GOOD QUESTIONS:
        "What game features characters building with blocks?" -> "minecraft"
        "Which streaming service produces The Crown series?" -> "netflix"
        "What social platform uses a bird logo?" -> "twitter"
        "Which company makes the iPhone?" -> "apple"

        EXAMPLES OF BAD QUESTIONS:
        "Who was the first person to..." (avoid superlatives)
        "Which celebrity recently..." (avoid time-sensitive)
        "What is the most popular..." (avoid rankings)
        "Who is currently leading..." (avoid current events)

        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer in lowercase]
        Fun Fact: [brief, verifiable fact about the answer]"""

    def _make_api_request(self, messages: list) -> Optional[Dict]:
        """Make a request to the Mistral AI API."""
        try:
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
                timeout=10
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
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
        except (IndexError, AttributeError) as e:
            logger.error(f"Failed to parse API response: {e}")
            return None, None, None

    def _is_valid_question(self, question: str, answer: str) -> bool:
        """Validate the generated question and answer."""
        is_valid, reason = validate_question_content(question, answer)
        if not is_valid:
            logger.debug(f"Question rejected: {reason}")
            return False
            
        # Check for complex terms
        if any(term in question.lower() for term in COMPLEX_TERMS):
            logger.debug("Question rejected: Contains complex terms")
            return False
        
        return True

    def get_trivia_question(self, excluded_questions: set) -> Optional[Tuple[str, str, str]]:
        """Get a trivia question from Mistral AI."""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                # Select a random category and subcategory
                category = random.choice(list(QUIZ_CATEGORIES.keys()))
                subcategory = random.choice(QUIZ_CATEGORIES[category])
                difficulty = random.choices(
                    ['easy', 'medium', 'hard'],
                    weights=[0.6, 0.3, 0.1]
                )[0]
                
                # Generate the prompt
                prompt = self._generate_prompt(category, subcategory, difficulty)
                
                # Make API request
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
                
                return question, answer, fun_fact
                
            except Exception as e:
                logger.error(f"Error generating question: {e}")
                attempts += 1
        
        # If all attempts fail, return a fallback question
        return self._get_fallback_question()

    def _get_fallback_question(self) -> Tuple[str, str, str]:
        """Provide a fallback question when API fails."""
        fallback_questions = [
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
                "What gaming console competes with Xbox?",
                "playstation",
                "PlayStation was originally developed as a Nintendo partnership."
            ),
            (
                "Which streaming service created The Mandalorian?",
                "disney+",
                "The Mandalorian was one of the launch shows for Disney+."
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
            )
        ]
        
        return random.choice(fallback_questions)