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
        self.max_question_attempts = 3
        self.max_main_attempts = 3
        self.question_check_delay = 2  # seconds to wait between question attempts

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
            
        # Start first question
        threading.Timer(2.0, self.next_question).start()
        return True

    def try_get_valid_question(self, attempt: int = 1) -> Optional[Question]:
        """Try to get a valid question, with multiple attempts."""
        if attempt > self.max_question_attempts:
            return None

        try:
            question_data = self.mistral.get_trivia_question(self.state.used_questions)
            if not question_data:
                logger.warning(f"Failed to get question data, attempt {attempt} of {self.max_question_attempts}")
                time.sleep(self.question_check_delay)  # Add delay between attempts
                return self.try_get_valid_question(attempt + 1)

            # Ensure we got all required question data
            if len(question_data) != 3:
                logger.warning(f"Invalid question data format, attempt {attempt}")
                time.sleep(self.question_check_delay)
                return self.try_get_valid_question(attempt + 1)

            question = Question(
                text=question_data[0],
                primary_answer=question_data[1],
                alternative_answers=set(),
                fun_fact=question_data[2],
                category="general",
                difficulty=3
            )

            # Skip if question was recently used
            question_hash = f"{question.text}:{question.primary_answer}"
            if question_hash in self.state.used_questions:
                logger.warning(f"Question was recently used, attempt {attempt}")
                time.sleep(self.question_check_delay)
                return self.try_get_valid_question(attempt + 1)

            # Validate question
            if not self.question_manager.prepare_question({
                "text": question.text,
                "answer": question.primary_answer,
                "fun_fact": question.fun_fact
            }):
                logger.warning(f"Question validation failed, attempt {attempt}")
                time.sleep(self.question_check_delay)
                return self.try_get_valid_question(attempt + 1)

            return question

        except Exception as e:
            logger.error(f"Error getting question: {e}")
            time.sleep(self.question_check_delay)
            return self.try_get_valid_question(attempt + 1)

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

        # Try to get a valid question with multiple attempts
        for main_attempt in range(self.max_main_attempts):
            try:
                question = self.try_get_valid_question()
                if question:
                    # Update state
                    self.state.current_question = question.text
                    self.state.current_answer = question.primary_answer
                    self.state.question_verifications[question.text] = question.fun_fact
                    self.state.used_questions.add(f"{question.text}:{question.primary_answer}")
                    self.state.question_time = datetime.now()
                    
                    # Send question
                    self.irc.send_channel_message(
                        self.state.channel,
                        question.text,
                        question=True,
                        number=self.state.question_number
                    )
                    
                    # Start timer for next question
                    self.state.timer = threading.Timer(
                        self.state.answer_timeout,
                        self.handle_timeout
                    )
                    self.state.timer.start()
                    return

            except Exception as e:
                logger.error(f"Error in next_question: {e}, attempt {main_attempt + 1}/{self.max_main_attempts}")
                if main_attempt == self.max_main_attempts - 1:  # Last attempt
                    logger.error("All question generation attempts failed")
                    self.end_game()
                    return
                continue

        # If we got here, all attempts failed
        logger.error("Failed to get valid question after all attempts")
        self.end_game()
        
    def handle_answer(self, username: str, answer: str) -> None:
        """Process a user's answer attempt."""
        if not self.state.is_answer_valid(
            answer,
            (datetime.now() - self.state.question_time).seconds
        ):
            return

        # Prevent duplicate answers from same user for current question
        answer_key = f"{username}:{answer}"
        if answer_key in self.state.current_round_answers:
            return
        self.state.current_round_answers.add(answer_key)
            
        if is_answer_match(answer, self.state.current_answer):
            # Prevent duplicate scoring
            current_answer_key = (username, answer, self.state.current_question)
            if self.state.last_correct_answer == current_answer_key:
                return
            self.state.last_correct_answer = current_answer_key

            # Calculate score
            elapsed_time = (datetime.now() - self.state.question_time).seconds
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
            
            # Send verification fact if available
            if fun_fact := self.state.question_verifications.get(
                self.state.current_question
            ):
                self.irc.send_channel_message(
                    self.state.channel,
                    f"💡 {fun_fact}"
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
            f"⏰ Time's up! The answer was: {self.state.current_answer}"
        )
        self.irc.send_channel_message(self.state.channel, timeout_msg, timeout=True)
        
        if fun_fact := self.state.question_verifications.get(
            self.state.current_question
        ):
            self.irc.send_channel_message(
                self.state.channel,
                f"💡 {fun_fact}"
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
                for i, entry in enumerate(leaderboard, 1):
                    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "•")
                    leader_msg = (
                        f"{medal} {entry['username']}: {entry['total_score']} "
                        f"({entry['correct_answers']} correct)"
                    )
                    self.irc.send_channel_message(self.state.channel, leader_msg)
        
        self.state = QuizState()
        self.score_tracker = ScoreTracker()
        
    def handle_message(self, message: IRCMessage) -> None:
        """Handle incoming IRC messages."""
        if message.channel not in IRC_CONFIG['channels']:
            return
            
        command, args = extract_command(message.content)
        
        # Handle commands
        if handler := self.command_handlers.get(command):
            handler(message.username, message.channel)
            return
            
        # Handle answer attempts during active quiz
        if (self.state.active and self.state.channel == message.channel and
            not message.content.startswith('!')):
            self.handle_answer(message.username, message.content)

    def _handle_quiz_command(self, username: str, channel: str) -> None:
        """Handle the !quiz command."""
        if not self.start_game(channel):
            self.irc.send_channel_message(
                channel,
                "❌ A quiz is already in progress!"
            )

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
            for i, entry in enumerate(leaderboard, 1):
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