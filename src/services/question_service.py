import logging
import json
import asyncio
from typing import Dict, Optional
import aiohttp
from mistralai.client import MistralClient
from mistralai.models.chat import ChatMessage, Role

logger = logging.getLogger(__name__)

class QuestionService:
    def __init__(self, api_key: str):
        self.client = MistralClient(api_key=api_key)
        self.fallback_questions = [
            {
                "id": "fallback_1",
                "question": "What programming language was Python named after?",
                "answer": "Monty Python",
                "fun_fact": "Guido van Rossum, Python's creator, was a fan of Monty Python's Flying Circus!"
            },
            {
                "id": "fallback_2",
                "question": "What year was the first version of Python released?",
                "answer": "1991",
                "fun_fact": "Python was conceived in the late 1980s and first released in 1991."
            },
            # Add more fallback questions as needed
        ]
        self._fallback_index = 0
        self._retry_count = 3
        self._retry_delay = 1  # seconds

    async def get_question(self) -> Dict[str, str]:
        """Get a trivia question, falling back to local questions if service fails"""
        for attempt in range(self._retry_count):
            try:
                return await self._fetch_question_from_mistral()
            except Exception as e:
                logger.warning(f"Failed to fetch question from Mistral (attempt {attempt + 1}): {e}")
                await asyncio.sleep(self._retry_delay)
        
        # If all retries failed, use fallback question
        logger.info("Using fallback question")
        return self._get_fallback_question()

    async def _fetch_question_from_mistral(self) -> Dict[str, str]:
        """Fetch a question from Mistral AI service"""
        messages = [
            {
                "role": "system",
                "content": "You are a trivia question generator. Generate a single trivia question with "
                          "an answer and an interesting fun fact. Return it in JSON format with keys: "
                          "'id' (unique string), 'question', 'answer' (keep it simple), and 'fun_fact'."
            },
            {
                "role": "user",
                "content": "Generate a trivia question"
            }
        ]

        try:
            response = self.client.chat(
                model="mistral-tiny",
                messages=messages
            )

            # Parse the response
            response_content = response.choices[0].message.content
            question_data = json.loads(response_content)

            # Validate the response format
            required_keys = {"id", "question", "answer", "fun_fact"}
            if not all(key in question_data for key in required_keys):
                raise ValueError("Invalid question format from Mistral")

            return question_data

        except Exception as e:
            logger.error(f"Error getting question from Mistral: {e}")
            raise

    def _get_fallback_question(self) -> Dict[str, str]:
        """Get a fallback question from the local collection"""
        question = self.fallback_questions[self._fallback_index]
        self._fallback_index = (self._fallback_index + 1) % len(self.fallback_questions)
        return question