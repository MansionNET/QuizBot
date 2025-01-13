"""Question management and tracking."""
import logging
from typing import Dict, Set, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class Question:
    """Represents a single quiz question."""
    def __init__(self, question_id: str, question: str, answer: str, fun_fact: str,
                 category: str = "general", difficulty: int = 2):
        self.id = question_id
        self.question = question
        self.answer = answer
        self.fun_fact = fun_fact
        self.category = category
        self.difficulty = difficulty
        self.asked_at: Optional[datetime] = None
        self.answered_at: Optional[datetime] = None
        self.answered_by: Optional[str] = None

class QuestionManager:
    """Manages quiz questions and their state."""
    def __init__(self, mistral_service):
        self.mistral_service = mistral_service
        self.used_questions: Set[str] = set()
        self.current_question: Optional[Question] = None
        self._retry_count = 3
        self._retry_delay = 1  # seconds
        
        # Improved fallback questions with categories and varying difficulty
        self.fallback_questions = [
            {
                "id": "fallback_1",
                "category": "technology",
                "difficulty": 2,
                "question": "What programming language was Python named after?",
                "answer": "Monty Python",
                "fun_fact": "Guido van Rossum, Python's creator, was a fan of Monty Python's Flying Circus!"
            },
            {
                "id": "fallback_2",
                "category": "history",
                "difficulty": 3,
                "question": "Which ancient wonder was located in Alexandria, Egypt?",
                "answer": "lighthouse",
                "fun_fact": "The Lighthouse of Alexandria stood over 300 feet tall and guided ships for centuries."
            },
            {
                "id": "fallback_3",
                "category": "science",
                "difficulty": 2,
                "question": "What is the hardest natural substance on Earth?",
                "answer": "diamond",
                "fun_fact": "Despite being the hardest natural substance, diamonds can be shattered with a hammer."
            },
            {
                "id": "fallback_4",
                "category": "geography",
                "difficulty": 1,
                "question": "Which is the largest ocean on Earth?",
                "answer": "Pacific",
                "fun_fact": "The Pacific Ocean covers more area than all Earth's continents combined."
            },
            {
                "id": "fallback_5",
                "category": "arts",
                "difficulty": 2,
                "question": "Which artist painted 'The Starry Night'?",
                "answer": "Van Gogh",
                "fun_fact": "Van Gogh painted 'The Starry Night' while in an asylum in Saint-Rémy-de-Provence."
            },
            {
                "id": "fallback_6",
                "category": "sports",
                "difficulty": 1,
                "question": "In which sport would you perform a slam dunk?",
                "answer": "basketball",
                "fun_fact": "The first slam dunk in basketball was performed by Joe Fortenberry in 1936."
            },
            {
                "id": "fallback_7",
                "category": "nature",
                "difficulty": 3,
                "question": "What is the only mammal that cannot jump?",
                "answer": "elephant",
                "fun_fact": "Elephants are the only mammals that can't jump because all four feet must be on the ground at once."
            }
        ]
        self._fallback_index = 0

    async def get_next_question(self) -> Optional[Question]:
        """Get the next question, either from Mistral or fallback."""
        try:
            # First attempt to get a question
            question_data = await self._get_question_with_retries()
            
            # If no question available, clear used set and try again
            if question_data is None:
                logger.info("No unused questions available, clearing used questions set")
                self.clear_used_questions()
                question_data = await self._get_question_with_retries()
                
            # If still no question, try fallback
            if question_data is None:
                logger.warning("No questions available from Mistral, using fallback")
                question_data = self._get_fallback_question()
                
            if question_data is None:
                logger.error("Failed to get question from any source")
                return None
                
            # Create and return the question with category and difficulty
            self.used_questions.add(question_data["id"])
            self.current_question = Question(
                question_id=question_data["id"],
                question=question_data["question"],
                answer=question_data["answer"],
                fun_fact=question_data["fun_fact"],
                category=question_data.get("category", "general"),
                difficulty=question_data.get("difficulty", 2)
            )
            self.current_question.asked_at = datetime.now()
            return self.current_question
            
        except Exception as e:
            logger.error(f"Error getting next question: {e}")
            return None

    async def _get_question_with_retries(self) -> Dict[str, str]:
        """Attempt to get a question from Mistral with retries."""
        last_error = None
        for attempt in range(self._retry_count):
            try:
                return await self.mistral_service.generate_question()
            except Exception as e:
                last_error = e
                logger.warning(f"Question generation attempt {attempt + 1} failed: {e}")
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
                
        raise Exception(f"Failed to get question after {self._retry_count} attempts: {last_error}")

    def _get_fallback_question(self) -> Dict[str, str]:
        """Get a fallback question from the local collection."""
        question = self.fallback_questions[self._fallback_index]
        self._fallback_index = (self._fallback_index + 1) % len(self.fallback_questions)
        return question

    def mark_answered(self, nick: str):
        """Mark the current question as answered."""
        if self.current_question:
            self.current_question.answered_at = datetime.now()
            self.current_question.answered_by = nick
            
    def is_question_used(self, question_id: str) -> bool:
        """Check if a question has been used in the current game."""
        return question_id in self.used_questions
        
    def clear_used_questions(self):
        """Clear the list of used questions."""
        self.used_questions.clear()
        self.current_question = None
