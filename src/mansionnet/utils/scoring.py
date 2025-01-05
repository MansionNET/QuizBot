"""Scoring utilities for the QuizBot."""
from typing import Dict, Tuple
from datetime import datetime

def calculate_base_points(elapsed_time: float, max_time: float, 
                        question_number: int) -> int:
    """Calculate base points for an answer based on time and question difficulty."""
    # Calculate points based on speed (1-10 points)
    time_points = max(1, int(10 * (1 - elapsed_time/max_time)))
    
    # Adjust points based on question difficulty (questions get harder as game progresses)
    if question_number <= 3:  # Easy questions
        return min(time_points, 5)  # Cap at 5 points
    elif question_number <= 7:  # Medium questions
        return min(time_points, 8)  # Cap at 8 points
    else:  # Hard questions
        return time_points  # Full points possible

def calculate_streak_multiplier(streak: int, bonus_rules: Dict) -> float:
    """Calculate point multiplier based on answer streak."""
    multiplier = 1.0
    for streak_req, bonus in sorted(bonus_rules['streak'].items(), reverse=True):
        if streak >= streak_req:
            multiplier = bonus
            break
    return multiplier

def calculate_speed_multiplier(time_remaining: float, bonus_rules: Dict) -> float:
    """Calculate point multiplier based on answer speed."""
    multiplier = 1.0
    for time_threshold, bonus in sorted(bonus_rules['speed'].items(), reverse=True):
        if time_remaining >= time_threshold:
            multiplier = bonus
            break
    return multiplier

def calculate_final_score(base_points: int, streak_multiplier: float, 
                         speed_multiplier: float) -> Tuple[int, float]:
    """Calculate final score with all multipliers applied."""
    total_multiplier = streak_multiplier * speed_multiplier
    final_points = int(base_points * total_multiplier)
    return final_points, total_multiplier

def format_score_message(username: str, points: int, base_points: int, 
                        multiplier: float) -> str:
    """Format a score message with bonus information."""
    if multiplier > 1:
        return (
            f"✨ {username} got {points} points! "
            f"(Base: {base_points} × Bonus: {multiplier:.1f})"
        )
    return f"✨ {username} got {points} points!"

class ScoreTracker:
    """Tracks scores and statistics during a quiz game."""
    
    def __init__(self):
        """Initialize score tracking."""
        self.scores: Dict[str, int] = {}
        self.streaks: Dict[str, int] = {}
        self.fastest_answers: Dict[str, float] = {}
        self.correct_answers: Dict[str, int] = {}
        self.total_questions_answered: int = 0
        
    def update_score(self, username: str, points: int, answer_time: float) -> None:
        """Update a player's score and statistics."""
        # Update basic score
        self.scores[username] = self.scores.get(username, 0) + points
        
        # Update streak
        self.streaks[username] = self.streaks.get(username, 0) + 1
        
        # Update fastest answer
        current_fastest = self.fastest_answers.get(username, float('inf'))
        if answer_time < current_fastest:
            self.fastest_answers[username] = answer_time
        
        # Update correct answers count
        self.correct_answers[username] = self.correct_answers.get(username, 0) + 1
        
        # Update total questions
        self.total_questions_answered += 1
    
    def reset_streak(self, username: str) -> None:
        """Reset a player's answer streak."""
        self.streaks[username] = 0
    
    def get_player_stats(self, username: str) -> Dict:
        """Get comprehensive statistics for a player."""
        return {
            'score': self.scores.get(username, 0),
            'streak': self.streaks.get(username, 0),
            'fastest_answer': self.fastest_answers.get(username, 0),
            'correct_answers': self.correct_answers.get(username, 0),
            'accuracy': (
                self.correct_answers.get(username, 0) / 
                self.total_questions_answered if self.total_questions_answered > 0 
                else 0
            )
        }
    
    def get_leaderboard(self, limit: int = 5) -> list:
        """Get the current leaderboard."""
        sorted_scores = sorted(
            self.scores.items(), 
            key=lambda x: (x[1], self.correct_answers.get(x[0], 0)), 
            reverse=True
        )
        return sorted_scores[:limit]
