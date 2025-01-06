"""Core quiz game logic."""
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from collections import defaultdict

from ..models.quiz_state import QuizState
from ..models.database import Database
from ..models.question import QuestionManager, Question
from ..services.mistral_service import MistralService
from ..services.irc_service import IRCService, IRCMessage
from ..utils.text_processing import is_answer_match, extract_command
from ..utils.scoring import (
    ScoreTracker, calculate_base_points, calculate_streak_multiplier,
    calculate_speed_multiplier, calculate_final_score, format_score_message
)
from ..config.settings import QUIZ_CONFIG, BONUS_RULES, IRC_CONFIG

logger = logging.getLogger(__name__)

class QuizGame:
    """Manages the quiz game flow and coordination between services."""
    
    def __init__(self):
        """Initialize the quiz game."""
        self.state = QuizState()
        self.db = Database()
        self.mistral = MistralService()
        self.score_tracker = ScoreTracker()
        self.irc = IRCService(message_handler=self.handle_message)
        self.question_manager = QuestionManager()
        self.command_handlers = self._init_command_handlers()

    def _init_command_handlers(self) -> Dict[str, Callable[[str, str], None]]:
        """Initialize command handlers mapping."""
        return {
            '!quiz': self._handle_quiz_command,
            '!help': self._handle_help_command,
            '!stats': self._handle_stats_command,
            '!leaderboard': self._handle_leaderboard_command,
            '!stop': self._handle_stop_command,
        }
        
    def start_game(self, channel: str) -> bool:
        """Start a new quiz game."""
        logger.info(f"Attempting to start new game in {channel}")
        if self.state.active:
            return False
            
        self.state = QuizState(
            active=True,
            channel=channel,
            total_questions=QUIZ_CONFIG['total_questions'],
            answer_timeout=QUIZ_CONFIG['answer_timeout']
        )
        self.score_tracker = ScoreTracker()
        
        # Send welcome message
        welcome_messages = [
            "🎯 New Quiz Starting!",
            "• Type your answer in the channel",
            f"• {self.state.answer_timeout} seconds per question",
            f"• {self.state.total_questions} questions total",
            "• Faster answers = More points",
            "• Get bonus points for answer streaks",
            "Type !help for detailed rules"
        ]
        
        for msg in welcome_messages:
            self.irc.send_channel_message(channel, msg, announcement=True)
            
        # Start first question after a short delay
        threading.Timer(2.0, self.next_question).start()
        return True

    def handle_message(self, message: IRCMessage) -> None:
        """Handle incoming IRC messages."""
        logger.debug(f"Handling message: {message.content}")
        
        if not message.content:
            return

        command, args = extract_command(message.content)
        logger.debug(f"Extracted command: {command}, args: {args}")
        
        # Handle commands
        if command in self.command_handlers:
            logger.info(f"Executing command handler for {command}")
            self.command_handlers[command](message.username, message.channel)
            return
            
        # Handle answer attempts during active quiz
        if (self.state.active and self.state.channel == message.channel
            and not message.content.startswith('!')):
            self.handle_answer(message.username, message.content)

    def _handle_quiz_command(self, username: str, channel: str) -> None:
        """Handle the !quiz command."""
        logger.info(f"Quiz command from {username} in {channel}")
        if not self.start_game(channel):
            self.irc.send_channel_message(
                channel,
                "❌ A quiz is already in progress!"
            )

    def next_question(self) -> None:
        """Progress to the next question."""
        if not self.state.active:
            return
            
        # Cancel existing timer if any
        if self.state.timer:
            self.state.timer.cancel()
            
        # Reset question-specific state
        self.state.reset_question_state()
        
        self.state.question_number += 1
        if self.state.question_number > self.state.total_questions:
            self.end_game()
            return

        # Get next question
        try:
            question = self.mistral.get_trivia_question(self.state.used_questions)
            if not question:
                logger.error("Failed to get valid question")
                self.end_game()
                return

            # Update state
            self.state.current_question = question[0]
            self.state.current_answer = question[1]
            self.state.fun_fact = question[2]
            self.state.question_time = datetime.now()
            
            # Send question
            self.irc.send_channel_message(
                self.state.channel,
                self.state.current_question,
                question=True,
                number=self.state.question_number
            )
            
            # Start timer for next question
            self.state.timer = threading.Timer(
                self.state.answer_timeout,
                self.handle_timeout
            )
            self.state.timer.start()
            
        except Exception as e:
            logger.error(f"Error in next_question: {e}")
            self.end_game()

    def handle_answer(self, username: str, answer: str) -> None:
        """Process a user's answer attempt."""
        if not self.state.active or not self.state.current_question:
            return
            
        # Calculate elapsed time
        elapsed_time = (datetime.now() - self.state.question_time).total_seconds()
        if elapsed_time >= self.state.answer_timeout:
            return

        # Check answer
        if is_answer_match(answer, self.state.current_answer):
            # Calculate score
            base_points = calculate_base_points(
                elapsed_time,
                self.state.answer_timeout,
                self.state.question_number
            )
            
            # Update streak before calculating multipliers
            self.score_tracker.update_streak(username)
            
            streak_multiplier = calculate_streak_multiplier(
                self.score_tracker.streaks.get(username, 0),
                BONUS_RULES
            )
            
            speed_multiplier = calculate_speed_multiplier(
                self.state.answer_timeout - elapsed_time,
                BONUS_RULES
            )
            
            points, total_multiplier = calculate_final_score(
                base_points,
                streak_multiplier,
                speed_multiplier
            )
            
            # Update scores
            self.score_tracker.update_score(username, points, elapsed_time)
            
            # Update database
            self.db.update_score(
                username,
                points,
                elapsed_time,
                self.score_tracker.streaks[username]
            )
            
            # Send success message with streak info
            streak = self.score_tracker.streaks.get(username, 0)
            streak_info = f" (Streak: {streak}x)" if streak > 1 else ""
            
            score_message = format_score_message(
                username,
                points,
                base_points,
                total_multiplier
            ) + streak_info
            
            self.irc.send_channel_message(self.state.channel, score_message)
            
            # Send fun fact
            if self.state.fun_fact:
                self.irc.send_channel_message(
                    self.state.channel,
                    f"💡 {self.state.fun_fact}"
                )
            
            # Move to next question after a short delay
            threading.Timer(2.0, self.next_question).start()
        else:
            self.score_tracker.reset_streak(username)
            
    def handle_timeout(self) -> None:
        """Handle question timeout."""
        if not self.state.active or not self.state.current_answer:
            return
            
        timeout_msg = (
            f"⏰ ⏰ Time's up! The answer was: {self.state.current_answer}"
        )
        self.irc.send_channel_message(self.state.channel, timeout_msg, timeout=True)
        
        if self.state.fun_fact:
            self.irc.send_channel_message(
                self.state.channel,
                f"💡 {self.state.fun_fact}"
            )
        
        # Reset all streaks on timeout
        for username in self.score_tracker.streaks:
            self.score_tracker.reset_streak(username)
            
        threading.Timer(2.0, self.next_question).start()
        
    def end_game(self) -> None:
        """End the current quiz game."""
        if not self.state.active:
            return
            
        self.state.active = False
        if self.state.timer:
            self.state.timer.cancel()
            
        # Get final scores
        final_scores = self.score_tracker.get_leaderboard()
        
        if final_scores:
            self.irc.send_channel_message(
                self.state.channel,
                "🏁 Final Results:",
                announcement=True
            )
            
            for username, score in final_scores:
                stats = self.score_tracker.get_player_stats(username)
                score_msg = (
                    f"{username}: {score} points "
                    f"({stats['correct_answers']} correct, "
                    f"best streak: {stats['streak']}x)"
                )
                self.irc.send_channel_message(self.state.channel, score_msg)
                
            # Show all-time leaderboard
            leaderboard = self.db.get_leaderboard()
            if leaderboard:
                self.irc.send_channel_message(
                    self.state.channel,
                    "🏆 All-Time Leaders:",
                    announcement=True
                )
                for i, entry in enumerate(leaderboard[:5], 1):
                    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "•")
                    leader_msg = (
                        f"{medal} {entry['username']}: {entry['total_score']} "
                        f"({entry['correct_answers']} correct)"
                    )
                    self.irc.send_channel_message(self.state.channel, leader_msg)
        
        self.state = QuizState()
        self.score_tracker = ScoreTracker()

    def _handle_help_command(self, username: str, channel: str) -> None:
        """Handle the !help command."""
        help_messages = [
            "📚 QuizBot Commands & Rules:",
            "!quiz - Start a new quiz game",
            "!stats - View your statistics",
            "!leaderboard - Show top players",
            "!stop - Stop current quiz (admin only)",
            "",
            "How to Play:",
            "• Answer questions directly in chat",
            "• Faster answers earn more points",
            "• Build streaks for bonus multipliers",
            f"• {QUIZ_CONFIG['answer_timeout']} seconds per question",
            f"• {QUIZ_CONFIG['total_questions']} questions per game"
        ]
        
        for msg in help_messages:
            self.irc.send_channel_message(channel, msg)

    def _handle_stats_command(self, username: str, channel: str) -> None:
        """Handle the !stats command."""
        stats = self.db.get_player_stats(username)
        if stats:
            stats_msg = (
                f"📊 Stats for {username}: "
                f"{stats['total_score']} total points, "
                f"{stats['correct_answers']} correct answers, "
                f"Best streak: {stats['longest_streak']}x, "
                f"Best time: {stats['fastest_answer']:.1f}s"
            )
            self.irc.send_channel_message(channel, stats_msg)
        else:
            self.irc.send_channel_message(
                channel,
                f"📊 No stats found for {username}"
            )

    def _handle_leaderboard_command(self, username: str, channel: str) -> None:
        """Handle the !leaderboard command."""
        leaderboard = self.db.get_leaderboard()
        if leaderboard:
            self.irc.send_channel_message(
                channel,
                "🏆 Top Quiz Masters:",
                announcement=True
            )
            for i, entry in enumerate(leaderboard[:5], 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "•")
                msg = (
                    f"{medal} {entry['username']}: {entry['total_score']} points "
                    f"({entry['correct_answers']} correct)"
                )
                self.irc.send_channel_message(channel, msg)
        else:
            self.irc.send_channel_message(
                channel,
                "No scores yet! Start a quiz with !quiz"
            )

    def _handle_stop_command(self, username: str, channel: str) -> None:
        """Handle the !stop command."""
        if username in IRC_CONFIG['admin_users']:
            self.end_game()
        else:
            self.irc.send_channel_message(
                channel,
                f"❌ Only administrators can stop the quiz"
            )

    def run(self) -> None:
        """Start the quiz bot."""
        try:
            self.irc.run()
        except Exception as e:
            logger.error(f"Fatal error in quiz game: {e}")
            raise