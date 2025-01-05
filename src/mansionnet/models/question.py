"""Question model and validation."""
from dataclasses import dataclass
from typing import Set, Tuple, List, Optional, Dict
import re
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class Question:
    """Structured question data with validation."""
    text: str
    primary_answer: str
    alternative_answers: Set[str]
    fun_fact: str
    category: str
    difficulty: int  # 1-5 scale

    def is_valid(self) -> bool:
        """Validate question structure and content."""
        return all([
            len(self.text) >= 10,
            len(self.primary_answer) >= 2,
            len(self.fun_fact) >= 20,
            1 <= self.difficulty <= 5
        ])
        
    @property
    def all_answers(self) -> Set[str]:
        """Get all valid answers including alternatives."""
        return {self.primary_answer} | self.alternative_answers

    def get_key(self) -> str:
        """Get unique key for this question."""
        return f"{self.category}:{self.text}"

class QuestionValidator:
    """Validates and improves question quality."""
    
    VALID_CATEGORIES = {
        "history", "science", "technology", "sports", "entertainment",
        "geography", "literature", "music", "movies", "gaming"
    }
    
    AMBIGUOUS_WORDS = {
        "thing", "stuff", "something", "anything",
        "many", "few", "some", "most", "best"
    }
    
    def __init__(self):
        self.used_questions = set()
        
    def validate_question(self, question: Question) -> Tuple[bool, str]:
        """Validate a question for quality and usability."""
        if not question.is_valid():
            return False, "Question missing required fields"
            
        question_key = question.get_key()
        if question_key in self.used_questions:
            return False, "Question was recently used"
            
        if not self._validate_question_text(question.text):
            return False, "Question text needs improvement"
            
        if not self._validate_answers(question.all_answers):
            return False, "Answer set needs improvement"
            
        self.used_questions.add(question_key)
        return True, "Question is valid"
        
    def _validate_question_text(self, text: str) -> bool:
        """Validate question text quality."""
        if len(text) < 10 or len(text) > 150:
            return False
            
        if not text.endswith('?'):
            return False
            
        word_count = len(text.split())
        ambiguous_count = sum(1 for word in text.lower().split() 
                            if word in self.AMBIGUOUS_WORDS)
                            
        if ambiguous_count / word_count > 0.3:
            return False
            
        return True
        
    def _validate_answers(self, answers: Set[str]) -> bool:
        """Validate answer set quality."""
        if not answers:
            return False
            
        if any(len(answer) < 2 for answer in answers):
            return False
            
        normalized_answers = {self._normalize_answer(a) for a in answers}
        if len(normalized_answers) != len(answers):
            return False
            
        return True
        
    def _normalize_answer(self, answer: str) -> str:
        """Normalize answer for comparison."""
        return re.sub(r'[^\w\s]', '', answer.lower().strip())

class QuestionManager:
    """Manages question generation, validation, and history."""
    
    QUESTION_HISTORY_FILE = "question_history.json"
    MAX_HISTORY_SIZE = 100  # Keep track of last 100 questions to avoid repeats
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize manager."""
        self.validator = QuestionValidator()
        self.current_questions: List[Question] = []
        self.question_history: Dict[str, dict] = {}
        self.base_dir = base_dir or Path(__file__).parent.parent / "data"
        self.history_path = self.base_dir / self.QUESTION_HISTORY_FILE
        
        # Load question history
        self._load_history()
        
    def _load_history(self) -> None:
        """Load question history from file."""
        try:
            if self.history_path.exists():
                with open(self.history_path) as f:
                    self.question_history = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load question history: {e}")
            self.question_history = {}
            
    def _save_history(self) -> None:
        """Save question history to file."""
        try:
            # Ensure directory exists
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_path, 'w') as f:
                json.dump(self.question_history, f)
        except Exception as e:
            logger.error(f"Failed to save question history: {e}")
            
    def was_recently_used(self, question: Question) -> bool:
        """Check if question was recently used."""
        key = question.get_key()
        return key in self.question_history
        
    def record_question_use(self, question: Question) -> None:
        """Record that a question was used."""
        key = question.get_key()
        self.question_history[key] = {
            'text': question.text,
            'answer': question.primary_answer,
            'category': question.category
        }
        
        # Trim history if too large
        if len(self.question_history) > self.MAX_HISTORY_SIZE:
            # Remove oldest entries
            sorted_keys = sorted(self.question_history.keys())
            for old_key in sorted_keys[:len(sorted_keys) - self.MAX_HISTORY_SIZE]:
                del self.question_history[old_key]
                
        self._save_history()
        
    def prepare_question(self, raw_question_data: dict) -> Optional[Question]:
        """Prepare and validate a question for use."""
        try:
            question = Question(
                text=raw_question_data['text'],
                primary_answer=raw_question_data['answer'],
                alternative_answers=set(raw_question_data.get('alternatives', [])),
                fun_fact=raw_question_data['fun_fact'],
                category=raw_question_data.get('category', 'general'),
                difficulty=raw_question_data.get('difficulty', 3)
            )
            
            # Check validity
            if not self.validator.validate_question(question)[0]:
                return None
                
            # Check if recently used
            if self.was_recently_used(question):
                return None
                
            # Record usage
            self.record_question_use(question)
            
            return question
            
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to prepare question: {e}")
            return None