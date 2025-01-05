"""Data model for quiz state management."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, List
import threading
from collections import defaultdict

@dataclass
class QuizState:
    """Represents the current state of a quiz game."""
    active: bool = False
    current_question: Optional[str] = None
    current_answer: Optional[str] = None
    question_time: Optional[datetime] = None
    scores: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    question_number: int = 0
    total_questions: int = 10
    answer_timeout: int = 30
    channel: Optional[str] = None
    timer: Optional[threading.Timer] = None
    used_questions: Set[str] = field(default_factory=set)
    question_verifications: Dict[str, str] = field(default_factory=dict)
    streak_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def reset(self) -> None:
        """Reset the quiz state to default values."""
        self.active = False
        self.current_question = None
        self.current_answer = None
        self.question_time = None
        self.scores.clear()
        self.question_number = 0
        self.channel = None
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self.used_questions.clear()
        self.question_verifications.clear()
        self.streak_counts.clear()

    def is_answer_valid(self, answer: str, elapsed_time: int) -> bool:
        """Check if an answer is valid given the current state."""
        return (
            self.active and
            self.current_answer and
            elapsed_time <= self.answer_timeout
        )