"""Core quiz game logic."""
import logging
import asyncio
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from collections import defaultdict

from ..models.quiz_state import QuizState
from ..models.database import Database
from ..models.question import QuestionManager, Question
from ..services.mistral_service import MistralService
from ..services.irc_service import IRCMessage, IRCService
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
        self.command_handlers = {
            '!quiz': self.handle_quiz_command,
            '!help': self.handle_help_command,
            '!stats': self.handle_stats_command,
            '!leaderboard': self.handle_leaderboard_command,
            '!stop': self.handle_stop_command,
        }
        self.lock = asyncio.Lock()
        self.question_task = None
        self.timeout_task = None
        self._tasks = set()
        self._stopping = False

    def _handle_task_exception(self, task):
        """Handle exceptions from tracked tasks."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass  # Task was cancelled, this is normal
        except Exception as e:
            logger.error(f"Task {task.get_name()} failed with exception: {e}",
                        exc_info=True)
    
    def _create_tracked_task(self, coro, name=None):
        """Create and track an asyncio task with error handling."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._handle_task_exception)
        return task

    async def handle_quiz_command(self, username: str, channel: str) -> None:
        """Handle the !quiz command."""
        logger.info(f"Quiz command from {username} in {channel}")
        if not await self.start_game(channel):
            await self.irc.send_channel_message(
                channel,
                "❌ A quiz is already in progress!"
            )

    async def handle_help_command(self, username: str, channel: str) -> None:
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
            await self.irc.send_channel_message(channel, msg)

    async def handle_stats_command(self, username: str, channel: str) -> None:
        """Handle the !stats command."""
        stats = await self.db.get_player_stats(username)
        if stats:
            stats_msg = (
                f"📊 Stats for {username}: "
                f"{stats['total_score']} total points, "
                f"{stats['correct_answers']} correct answers, "
                f"Best streak: {stats['longest_streak']}x, "
                f"Best time: {stats['fastest_answer']:.1f}s"
            )
            await self.irc.send_channel_message(channel, stats_msg)
        else:
            await self.irc.send_channel_message(
                channel,
                f"📊 No stats found for {username}"
            )

    async def handle_leaderboard_command(self, username: str, channel: str) -> None:
        """Handle the !leaderboard command."""
        leaderboard = await self.db.get_leaderboard()
        if leaderboard:
            await self.irc.send_channel_message(
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
                await self.irc.send_channel_message(channel, msg)
        else:
            await self.irc.send_channel_message(
                channel,
                "No scores yet! Start a quiz with !quiz"
            )

    async def handle_stop_command(self, username: str, channel: str) -> None:
        """Handle the !stop command."""
        if username in IRC_CONFIG['admin_users']:
            await self.end_game()
        else:
            await self.irc.send_channel_message(
                channel,
                f"❌ Only administrators can stop the quiz"
            )

    async def cleanup(self):
        """Cleanup all resources and shutdown gracefully."""
        self._stopping = True
        
        # End any active game
        await self.end_game()
        
        # Cancel all tracked tasks
        if self._tasks:
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for all tasks to complete with timeout
            try:
                async with asyncio.timeout(5.0):  # 5 second timeout for cleanup
                    await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                logger.error("Cleanup timed out, some tasks may not have finished")
        
        # Cleanup IRC connection
        await self.irc.disconnect()
        
        # Cleanup database connections
        await self.db.close()

    async def handle_message(self, message: IRCMessage) -> None:
        """Handle incoming IRC messages."""
        if not message.content:
            return

        command, args = extract_command(message.content)
        logger.debug(f"Extracted command: {command}, args: {args}")
        
        # Handle commands
        if command in self.command_handlers:
            try:
                async with asyncio.timeout(5.0):  # 5 second timeout
                    await self.command_handlers[command](message.username, message.channel)
            except asyncio.TimeoutError:
                logger.error(f"Command {command} timed out")
            return
            
        # Handle answer attempts during active quiz
        if (self.state.active and self.state.channel == message.channel
            and not message.content.startswith('!')):
            await self.handle_answer(message.username, message.content)

    async def run(self) -> None:
        """Start the quiz bot."""
        try:
            await self.irc.run()
        except Exception as e:
            logger.error(f"Fatal error in quiz game: {e}")
            raise

    async def end_game(self) -> None:
        """End the current quiz game."""
        async with self.lock:
            if not self.state.active:
                return
                
            self.state.active = False
            
            # Cancel running tasks properly
            if self.timeout_task and not self.timeout_task.done():
                self.timeout_task.cancel()
                try:
                    await self.timeout_task
                except asyncio.CancelledError:
                    pass
                    
            if self.question_task and not self.question_task.done():
                self.question_task.cancel()
                try:
                    await self.question_task
                except asyncio.CancelledError:
                    pass

            # Get final scores
            final_scores = self.score_tracker.get_leaderboard()
            logger.info("Ending game with final scores: %s", final_scores)
            
            if final_scores:
                await self.irc.send_channel_message(
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
                    await self.irc.send_channel_message(self.state.channel, score_msg)
                    
                # Add delay to ensure DB updates are complete
                await asyncio.sleep(1)
                    
                # Show all-time leaderboard
                leaderboard = await self.db.get_leaderboard()
                logger.info("Retrieved leaderboard: %s", leaderboard)
                
                if leaderboard:
                    await self.irc.send_channel_message(
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
                        await self.irc.send_channel_message(self.state.channel, leader_msg)
                else:
                    logger.warning("No leaderboard data found at end of game")
            else:
                logger.warning("No final scores found at end of game")
            
            self.state = QuizState()
            self.score_tracker = ScoreTracker()

    async def handle_answer(self, username: str, answer: str) -> None:
        """Process a user's answer attempt."""
        async with self.lock:
            if not self.state.active or not self.state.current_question:
                return
                
            # Calculate elapsed time
            elapsed_time = self.state.get_elapsed_time()
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
                await self.db.update_score(
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
                
                await self.irc.send_channel_message(self.state.channel, score_message)
                
                # Send fun fact
                if self.state.fun_fact:
                    await self.irc.send_channel_message(
                        self.state.channel,
                        f"💡 {self.state.fun_fact}"
                    )
                
                # Cancel timeout task
                if self.timeout_task and not self.timeout_task.done():
                    self.timeout_task.cancel()
                    
                # Check if this was the last question
                if self.state.question_number >= self.state.total_questions:
                    await self.end_game()
                else:
                    # Schedule next question
                    await asyncio.sleep(2)
                    self.question_task = self._create_tracked_task(
                        self.next_question(),
                        f"question_task_{self.state.question_number + 1}"
                    )
            else:
                self.score_tracker.reset_streak(username)

    async def start_game(self, channel: str) -> bool:
        """Start a new quiz game."""
        async with self.lock:
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
                await self.irc.send_channel_message(channel, msg, announcement=True)
                
            # Schedule first question
            self.question_task = self._create_tracked_task(
                self.next_question(),
                "question_task_1"
            )
            return True

    async def next_question(self) -> None:
        """Progress to the next question."""
        async with self.lock:
            if not self.state.active or self._stopping:
                return
                
            # Cancel existing timers properly
            if self.timeout_task and not self.timeout_task.done():
                self.timeout_task.cancel()
                try:
                    await self.timeout_task
                except asyncio.CancelledError:
                    pass
                
            # Reset question-specific state
            self.state.reset_question_state()
            
            self.state.question_number += 1
            if self.state.question_number > self.state.total_questions:
                await self.end_game()
                return

            # Get next question
            try:
                question = await self.mistral.get_trivia_question(self.state.used_questions)
                if not question:
                    logger.error("Failed to get valid question")
                    await self.end_game()
                    return

                # Update state
                self.state.current_question = question[0]
                self.state.current_answer = question[1]
                self.state.fun_fact = question[2]
                self.state.question_time = datetime.now()
                
                # Add question to used set
                question_hash = f"{question[0]}:{question[1]}"
                self.state.used_questions.add(question_hash)
                
                # Send question
                await self.irc.send_channel_message(
                    self.state.channel,
                    self.state.current_question,
                    question=True,
                    number=self.state.question_number
                )
                
                # Schedule timeout with tracking
                self.timeout_task = self._create_tracked_task(
                    self.handle_timeout(self.state.answer_timeout),
                    name=f"timeout_task_{self.state.question_number}"
                )
                
            except Exception as e:
                logger.error(f"Error in next_question: {e}")
                await self.end_game()

    async def handle_timeout(self, delay: int) -> None:
        """Handle question timeout."""
        await asyncio.sleep(delay)
        
        async with self.lock:
            if not self.state.active or not self.state.current_answer:
                return
                
            timeout_msg = (
                f"⏰ Time's up! The answer was: {self.state.current_answer}"
            )
            await self.irc.send_channel_message(self.state.channel, timeout_msg, timeout=True)
            
            if self.state.fun_fact:
                await self.irc.send_channel_message(
                    self.state.channel,
                    f"💡 {self.state.fun_fact}"
                )
            
            # Reset all streaks on timeout
            for username in self.score_tracker.streaks:
                self.score_tracker.reset_streak(username)
                
            await asyncio.sleep(2)
            
            # Check if this was the last question
            if self.state.question_number >= self.state.total_questions:
                await self.end_game()
            else:
                self.question_task = self._create_tracked_task(
                    self.next_question(),
                    f"question_task_{self.state.question_number + 1}"
                )