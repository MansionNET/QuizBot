"""Quiz state model."""
from datetime import datetime
from typing import Optional, Set
import threading

class QuizState:
    """Tracks the current state of a quiz game."""
    
    def __init__(self, active=False, channel=None, total_questions=10, answer_timeout=30):
        self.active = active
        self.channel = channel
        self.total_questions = total_questions
        self.answer_timeout = answer_timeout
        
        self.question_number = 0
        self.current_question = None
        self.current_answer = None
        self.question_time = None
        self.timer: Optional[threading.Timer] = None
        self.used_questions: Set[str] = set()
        self.question_verifications = {}
        
        # New fields for improved tracking
        self.last_correct_answer = None  # Tuple of (username, answer, question)
        self.current_round_answers = set()  # Track all answers per question
        
    def is_answer_valid(self, answer: str, elapsed_seconds: int) -> bool:
        """Check if an answer attempt is valid in the current state."""
        return (
            self.active and 
            self.current_answer and 
            elapsed_seconds < self.answer_timeout and
            len(answer.strip()) > 0
        )
        
    def reset_question_state(self):
        """Reset per-question state tracking."""
        self.last_correct_answer = None
        self.current_round_answers = set()