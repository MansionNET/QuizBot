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
        self.fun_fact: Optional[str] = None
        
        # Answer tracking
        self.current_round_answers: Set[str] = set()
        self.last_correct_answer: Optional[Tuple[str, str, str]] = None
        self.used_questions: Set[str] = set()
        self.question_verifications: Dict[str, str] = {}
        
        # Timer
        self.timer: Optional[Timer] = None

    def get_elapsed_time(self) -> float:
        """Safely calculate elapsed time."""
        if not self.question_time:
            return float('inf')
        
        now = datetime.now()
        return (now - self.question_time).total_seconds()

    def is_answer_valid(self, answer: str, elapsed_seconds: Optional[float] = None) -> bool:
        """Check if an answer attempt is valid."""
        if not self.active or not self.current_question or self.question_lock:
            return False

        if elapsed_seconds is None:
            elapsed_seconds = self.get_elapsed_time()

        return elapsed_seconds < self.answer_timeout

    def reset_question_state(self) -> None:
        """Reset state for a new question."""
        self.current_round_answers.clear()
        self.last_correct_answer = None
        self.question_time = datetime.now()
        self.question_lock = False
        self.fun_fact = None
        
    def can_ask_question(self) -> bool:
        """Check if we can ask a new question."""
        if not self.active or self.question_lock:
            return False
            
        if self.last_question_time:
            time_since_last = (datetime.now() - self.last_question_time).total_seconds()
            return time_since_last >= 2
            
        return True
        
    def lock_question(self) -> None:
        """Lock question state to prevent duplicate questions."""
        self.question_lock = True
        
    def unlock_question(self) -> None:
        """Unlock question state."""
        self.question_lock = False
        
    def update_question_time(self) -> None:
        """Update question timing."""
        self.last_question_time = datetime.now()