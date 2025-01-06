"""Quiz state model."""
from threading import Timer
from typing import Optional, Set, Dict, Tuple
from datetime import datetime


class QuizState:
    """Maintains the state of an active quiz game."""

    def __init__(self, active: bool = False, channel: str = "", 
                 total_questions: int = 10, answer_timeout: int = 30):
        """Initialize quiz state."""
        self.active = active
        self.channel = channel
        self.total_questions = total_questions
        self.answer_timeout = answer_timeout
        
        # Question state
        self.question_number = 0
        self.current_question: Optional[str] = None
        self.current_answer: Optional[str] = None
        self.question_time: Optional[datetime] = None
        self.last_question_time: Optional[datetime] = None
        self.question_lock = False
        
        # Answer tracking
        self.current_round_answers: Set[str] = set()
        self.last_correct_answer: Optional[Tuple[str, str, str]] = None
        self.used_questions: Set[str] = set()
        self.question_verifications: Dict[str, str] = {}
        
        # Timer
        self.timer: Optional[Timer] = None

    def is_answer_valid(self, answer: str, elapsed_seconds: int) -> bool:
        """Check if an answer attempt is valid."""
        return (
            self.active and 
            self.current_question is not None and
            not self.question_lock and
            elapsed_seconds < self.answer_timeout
        )

    def reset_question_state(self) -> None:
        """Reset state for a new question."""
        self.current_round_answers.clear()
        self.last_correct_answer = None
        self.question_time = datetime.now()
        self.question_lock = False
        
    def can_ask_question(self) -> bool:
        """Check if we can ask a new question."""
        return (
            self.active and
            not self.question_lock and
            (self.last_question_time is None or
             (datetime.now() - self.last_question_time).total_seconds() >= 2)
        )
        
    def lock_question(self) -> None:
        """Lock question state to prevent duplicate questions."""
        self.question_lock = True
        
    def unlock_question(self) -> None:
        """Unlock question state."""
        self.question_lock = False
        
    def update_question_time(self) -> None:
        """Update question timing."""
        self.last_question_time = datetime.now()