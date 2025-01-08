"""Quiz state model."""
from datetime import datetime
from typing import Optional, Set, Dict, Tuple, List, Any
from collections import deque
from ..config.settings import QUIZ_CONFIG

class QuizState:
    """Manages the state of an active quiz game."""
    
    def __init__(
        self,
        active: bool = False,
        channel: str = "",
        total_questions: int = 10,
        answer_timeout: int = 30,
        max_used_questions: Optional[int] = None,
        max_players: Optional[int] = None
    ):
        # Game settings
        self.active = active
        self.channel = channel
        self.total_questions = total_questions
        self.answer_timeout = answer_timeout
        self.max_used_questions = max_used_questions or QUIZ_CONFIG.get('max_used_questions', 1000)
        self.min_answer_time = QUIZ_CONFIG.get('min_answer_time', 0.1)
        self.max_players = max_players or QUIZ_CONFIG.get('max_players_per_game', 50)
        
        # Question state
        self.question_number = 0
        self.current_question: Optional[str] = None
        self.current_answer: Optional[str] = None
        self.question_time: Optional[datetime] = None
        self.last_question_time: Optional[datetime] = None
        self.question_lock = False
        self.fun_fact: Optional[str] = None
        
        # Answer tracking with memory limits
        self.current_round_answers: Set[str] = set()
        self.last_correct_answer: Optional[Tuple[str, str, float]] = None  # username, answer, time
        self._used_questions: deque[str] = deque(maxlen=self.max_used_questions)  # FIFO queue with size limit
        self.question_verifications: Dict[str, str] = {}
        
        # Player tracking
        self._players: Dict[str, Dict[str, Any]] = {}  # Track player stats
        self._player_last_answer: Dict[str, float] = {}  # Rate limiting
        self._answer_history: List[Dict[str, Any]] = []  # Limited answer history
        self.max_answer_history = QUIZ_CONFIG.get('max_answer_history', 100)

    def add_player(self, username: str) -> bool:
        """Add a player to the game if space available."""
        if len(self._players) >= self.max_players:
            return False
        if username not in self._players:
            self._players[username] = {
                'join_time': datetime.now(),
                'answers': 0,
                'correct_answers': 0,
                'last_answer_time': None
            }
        return True

    def remove_player(self, username: str) -> None:
        """Remove a player from the game."""
        self._players.pop(username, None)
        self._player_last_answer.pop(username, None)

    def update_player_answer(self, username: str, was_correct: bool, answer_time: float) -> None:
        """Update player statistics after an answer."""
        if username in self._players:
            self._players[username]['answers'] += 1
            if was_correct:
                self._players[username]['correct_answers'] += 1
            self._players[username]['last_answer_time'] = datetime.now()
            self._player_last_answer[username] = answer_time

    def can_player_answer(self, username: str) -> bool:
        """Check if a player can answer based on rate limiting."""
        if username not in self._player_last_answer:
            return True
        
        min_time_between_answers = QUIZ_CONFIG.get('min_time_between_answers', 0.5)
        last_answer_time = self._player_last_answer.get(username, 0)
        current_time = datetime.now().timestamp()
        
        return (current_time - last_answer_time) >= min_time_between_answers

    def add_answer_to_history(self, username: str, answer: str, was_correct: bool) -> None:
        """Add an answer to the history with size limit."""
        self._answer_history.append({
            'username': username,
            'answer': answer,
            'was_correct': was_correct,
            'time': datetime.now(),
            'question_number': self.question_number
        })
        
        # Maintain history size limit
        while len(self._answer_history) > self.max_answer_history:
            self._answer_history.pop(0)

    @property
    def used_questions(self) -> Set[str]:
        """Get the set of used questions."""
        return set(self._used_questions)

    def add_used_question(self, question_hash: str) -> None:
        """Add a question to the used questions queue."""
        if question_hash not in self._used_questions:
            self._used_questions.append(question_hash)

    def get_elapsed_time(self) -> float:
        """Calculate elapsed time since current question was asked."""
        if not self.question_time:
            return float('inf')
            
        try:
            elapsed = (datetime.now() - self.question_time).total_seconds()
            return max(0, elapsed)  # Ensure non-negative time
        except Exception as e:
            # Handle potential datetime errors
            return float('inf')

    def is_answer_valid(
        self,
        username: str,
        answer: str,
        elapsed_seconds: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Check if an answer is valid considering timing and game state.
        Returns (is_valid, reason)
        """
        if not self.active:
            return False, "Game not active"
            
        if not self.current_question:
            return False, "No active question"
            
        if self.question_lock:
            return False, "Question locked"
            
        if not self.can_player_answer(username):
            return False, "Answer rate limit"
            
        if elapsed_seconds is None:
            elapsed_seconds = self.get_elapsed_time()
            
        # Validate timing
        if elapsed_seconds < self.min_answer_time:
            return False, "Answer too fast"
            
        if elapsed_seconds >= self.answer_timeout:
            return False, "Time expired"
            
        # Basic answer validation
        if not answer or len(answer.strip()) == 0:
            return False, "Empty answer"
            
        answer_len_limit = QUIZ_CONFIG.get('max_answer_length', 50)
        if len(answer) > answer_len_limit:
            return False, "Answer too long"
            
        return True, "Valid answer"

    def reset_question_state(self) -> None:
        """Reset the state for a new question."""
        self.current_round_answers.clear()
        self.last_correct_answer = None
        self.question_time = datetime.now()
        self.question_lock = False
        self.fun_fact = None
        
    def can_ask_question(self) -> bool:
        """Check if it's valid to ask a new question."""
        if not self.active or self.question_lock:
            return False
            
        if self.last_question_time:
            try:
                time_since_last = (datetime.now() - self.last_question_time).total_seconds()
                min_question_delay = QUIZ_CONFIG.get('question_delay', 2)
                return time_since_last >= min_question_delay
            except Exception:
                return True  # If datetime calculation fails, allow question
                
        return True
        
    def lock_question(self) -> None:
        """Lock the current question to prevent multiple answers."""
        self.question_lock = True
        
    def unlock_question(self) -> None:
        """Unlock the question state."""
        self.question_lock = False
        
    def update_question_time(self) -> None:
        """Update the last question time to current time."""
        self.last_question_time = datetime.now()
        
    def get_game_progress(self) -> Tuple[int, int]:
        """Get current game progress."""
        return (self.question_number, self.total_questions)
        
    def is_game_complete(self) -> bool:
        """Check if the game is complete."""
        return self.question_number >= self.total_questions
        
    def validate_state(self) -> Tuple[bool, str]:
        """Validate the internal consistency of the game state."""
        if self.active:
            if not self.channel:
                return False, "No channel set"
                
            if self.question_number > self.total_questions:
                return False, "Question number exceeds total"
                
            if self.question_number > 0 and not self.last_question_time:
                return False, "Missing last question time"
                
            if len(self._players) > self.max_players:
                return False, "Too many players"
                
        return True, "Valid state"

    def get_player_stats(self, username: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific player."""
        return self._players.get(username)

    def get_answer_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent answer history."""
        if limit:
            return self._answer_history[-limit:]
        return self._answer_history.copy()