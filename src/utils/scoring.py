"""Score calculation and tracking utilities."""
import logging
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class PlayerScore:
    """Represents a player's score and stats for a game session."""
    total_score: int = 0
    correct_answers: int = 0
    current_streak: int = 0
    best_streak: int = 0
    last_answer_time: Optional[datetime] = None
    fastest_answer: Optional[float] = None  # in seconds

@dataclass
class ScoreTracker:
    """Tracks scores for all players in a game session."""
    scores: Dict[str, PlayerScore] = field(default_factory=dict)
    
    def get_player_score(self, nick: str) -> PlayerScore:
        """Get or create a player's score record.
        
        Args:
            nick: Player's nickname
            
        Returns:
            PlayerScore: Player's score object
        """
        if nick not in self.scores:
            self.scores[nick] = PlayerScore()
        return self.scores[nick]
    
    def update_player_score(
        self,
        nick: str,
        points: int,
        answer_time: float
    ):
        """Update a player's score and stats.
        
        Args:
            nick: Player's nickname
            points: Points to add
            answer_time: Time taken to answer in seconds
        """
        player = self.get_player_score(nick)
        player.total_score += points
        player.correct_answers += 1
        player.current_streak += 1
        player.best_streak = max(player.best_streak, player.current_streak)
        
        if player.fastest_answer is None or answer_time < player.fastest_answer:
            player.fastest_answer = answer_time
            
    def reset_streak(self, nick: str):
        """Reset a player's current streak.
        
        Args:
            nick: Player's nickname
        """
        if nick in self.scores:
            self.scores[nick].current_streak = 0
            
    def clear_scores(self):
        """Clear all scores and stats."""
        self.scores.clear()

def calculate_base_points(difficulty: str = 'normal') -> int:
    """Calculate base points for a correct answer.
    
    Args:
        difficulty: Question difficulty ('easy', 'normal', 'hard')
        
    Returns:
        int: Base points for the answer
    """
    difficulty_multipliers = {
        'easy': 0.75,
        'normal': 1.0,
        'hard': 1.5
    }
    base = 100
    multiplier = difficulty_multipliers.get(difficulty.lower(), 1.0)
    return int(base * multiplier)

def calculate_streak_multiplier(streak: int, max_multiplier: float = 2.0) -> float:
    """Calculate multiplier based on answer streak.
    
    Args:
        streak: Current correct answer streak
        max_multiplier: Maximum multiplier allowed
        
    Returns:
        float: Streak multiplier value
    """
    # Each correct answer adds 10% up to max_multiplier
    multiplier = 1.0 + (streak * 0.1)
    return min(multiplier, max_multiplier)

def calculate_speed_multiplier(
    answer_time: float,
    time_limit: float,
    max_multiplier: float = 2.0,
    min_multiplier: float = 1.0
) -> float:
    """Calculate multiplier based on answer speed.
    
    Args:
        answer_time: Time taken to answer in seconds
        time_limit: Maximum time allowed for answer
        max_multiplier: Maximum multiplier allowed
        min_multiplier: Minimum multiplier allowed
        
    Returns:
        float: Speed multiplier value
    """
    if answer_time >= time_limit:
        return min_multiplier
        
    # Linear scaling between max and min multiplier based on time taken
    multiplier = max_multiplier - (answer_time / time_limit) * (max_multiplier - min_multiplier)
    return max(min_multiplier, min(max_multiplier, multiplier))

def calculate_final_score(
    base_points: int,
    streak_mult: float,
    speed_mult: float
) -> int:
    """Calculate final score with all multipliers applied.
    
    Args:
        base_points: Base points for the answer
        streak_mult: Streak multiplier
        speed_mult: Speed multiplier
        
    Returns:
        int: Final score after applying multipliers
    """
    return int(base_points * streak_mult * speed_mult)

def format_score_message(
    nick: str,
    points: int,
    streak: int,
    answer_time: float
) -> str:
    """Format a score message for IRC.
    
    Args:
        nick: Player's nickname
        points: Points earned
        streak: Current streak
        answer_time: Time taken to answer
        
    Returns:
        str: Formatted score message
    """
    streak_msg = f"(streak: {streak}x)" if streak > 1 else ""
    time_msg = f"[{answer_time:.1f}s]"
    return f"🎉 Correct, {nick}! +{points} points {streak_msg} {time_msg}"