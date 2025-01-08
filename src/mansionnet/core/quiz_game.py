"""Core quiz game logic."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any
from collections import defaultdict

from ..models.quiz_state import QuizState
from ..models.database import Database
from ..models.question import QuestionManager
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
    def __init__(self):
        self.logger = logging.getLogger(__name__)
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

    async def _cancel_tasks_safely(self, tasks):
        """Helper method to safely cancel tasks without recursion."""
        if not tasks:
            return
            
        for task in tasks:
            if not task.done() and not task.cancelled():
                task.cancel()
        
        try:
            await asyncio.wait(tasks, timeout=5.0)
        except Exception as e:
            self.logger.error(f"Error waiting for tasks to cancel: {e}")

    def _create_tracked_task(self, coro, name=None):
        """Create a tracked task with proper exception handling."""
        if self._stopping:
            self.logger.debug(f"Not creating new task {name} while stopping")
            return None
            
        task = asyncio.create_task(coro, name=name)
        
        def cleanup_task(t):
            try:
                self._tasks.discard(t)
                exc = t.exception()
                if exc:
                    self.logger.error(f"Task {t.get_name()} failed: {exc}")
            except (asyncio.CancelledError, RuntimeError):
                pass
                
        task.add_done_callback(cleanup_task)
        self._tasks.add(task)
        return task

    async def run(self) -> None:
        """Main run method for the quiz game."""
        try:
            await self.irc.run()
        except Exception as e:
            logger.error(f"Fatal error in quiz game: {e}")
            raise

    async def handle_quiz_command(self, username: str, channel: str) -> None:
        self.logger.info(f"Quiz command from {username} in {channel}")
        try:
            async with asyncio.timeout(45.0):
                if not await self.start_game(channel):
                    try:
                        await self.handle_timeout(0)
                    except Exception as e:
                        logger.error(f"Error in next_question: {e}")
                        await self.end_game()
        except asyncio.TimeoutError:
            logger.error("Quiz initialization timed out")
            await self.irc.send_channel_message(
                channel,
                "❌ Failed to start quiz. Please try again."
            )

    async def handle_timeout(self, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            
            async with self.lock:
                if not self.state.active or not self.state.current_answer:
                    return
                    
                timeout_msg = f"⏰ Time's up! The answer was: {self.state.current_answer}"
                await self.irc.send_channel_message(self.state.channel, timeout_msg, timeout=True)
                
                if self.state.fun_fact:
                    await self.irc.send_channel_message(
                        self.state.channel,
                        f"💡 {self.state.fun_fact}"
                    )
                
                # Reset all player streaks on timeout
                for username in self.score_tracker.streaks:
                    self.score_tracker.reset_streak(username)
                    
                await asyncio.sleep(2)
                
                if self.state.question_number >= self.state.total_questions:
                    self.logger.info("All questions completed after timeout, ending game")
                    self._create_tracked_task(self.end_game(), "end_game_timeout")
                elif self.state.active:  # Check if game is still active
                    self.logger.debug("Starting next question after timeout")
                    self.question_task = self._create_tracked_task(
                        self.next_question(),
                        f"question_task_timeout_{self.state.question_number + 1}"
                    )
                    
        except Exception as e:
            logger.error(f"Error in handle_timeout: {e}")
            await self.end_game()

    async def _display_final_scores(self):
        """Display final scores and leaderboard."""
        try:
            final_scores = self.score_tracker.get_leaderboard()
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
                    
                await asyncio.sleep(1)
                    
                leaderboard = await self.db.get_leaderboard()
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
        except Exception as e:
            logger.error(f"Error displaying final scores: {e}")
            raise

    async def end_game(self) -> None:
        """End the current game and cleanup resources."""
        async with self.lock:
            if not self.state.active:
                return
                
            self.logger.info("Ending game...")
            self.state.active = False
            
            # Display final scores before cleanup
            try:
                await self._display_final_scores()
            except Exception as e:
                self.logger.error(f"Error displaying final scores: {e}")
                
            # Now proceed with cleanup
            self._stopping = True
            
            # Collect tasks before cancellation
            tasks_to_cancel = set()
            
            # Add main tasks
            if self.timeout_task and not self.timeout_task.done():
                tasks_to_cancel.add(self.timeout_task)
            if self.question_task and not self.question_task.done():
                tasks_to_cancel.add(self.question_task)
                
            # Add tracked tasks
            tasks_to_cancel.update(t for t in self._tasks if not t.done())
            
            # Clear task references before cancellation
            self.timeout_task = None
            self.question_task = None
            self._tasks.clear()
            
            # Cancel all tasks
            await self._cancel_tasks_safely(tasks_to_cancel)
            
            # Reset state
            self.state = QuizState()
            self.score_tracker = ScoreTracker()
            self.logger.debug("Game state reset completed")

    async def handle_help_command(self, username: str, channel: str) -> None:
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
            await asyncio.sleep(0.1)  # Small delay between messages
        return True

    async def handle_stats_command(self, username: str, channel: str) -> None:
        if not username:
            logger.warning("Received stats command with no username")
            return False
            
        try:
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
            await asyncio.sleep(0.1)  # Small delay after sending message
            return True
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
            await self.irc.send_channel_message(
                channel,
                "❌ Error retrieving stats. Please try again."
            )
            return False

    async def handle_leaderboard_command(self, username: str, channel: str) -> bool:
        if not channel:
            logger.warning("Received leaderboard command with no channel")
            return False
            
        try:
            leaderboard = await self.db.get_leaderboard()
            if leaderboard:
                # Send header
                await self.irc.send_channel_message(
                    channel,
                    "🏆 Top Quiz Masters:",
                    announcement=True
                )
                await asyncio.sleep(0.1)  # Small delay between messages
                
                # Send each entry with a small delay
                for i, entry in enumerate(leaderboard[:5], 1):
                    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "•")
                    msg = (
                        f"{medal} {entry['username']}: {entry['total_score']} points "
                        f"({entry['correct_answers']} correct)"
                    )
                    await self.irc.send_channel_message(channel, msg)
                    await asyncio.sleep(0.1)  # Small delay between messages
                
                await asyncio.sleep(0.2)  # Final delay before returning
                return True
            else:
                await self.irc.send_channel_message(
                    channel,
                    "No scores yet! Start a quiz with !quiz"
                )
                await asyncio.sleep(0.1)  # Small delay after message
                return True
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            await self.irc.send_channel_message(
                channel,
                "❌ Error retrieving leaderboard. Please try again."
            )
            return False

    async def handle_stop_command(self, username: str, channel: str) -> None:
        if not username or not channel:
            logger.warning("Received stop command with missing parameters")
            return False
            
        if username in IRC_CONFIG['admin_users']:
            await self.end_game()
            await self.irc.send_channel_message(
                channel,
                "Quiz stopped by administrator."
            )
            await asyncio.sleep(0.1)  # Small delay after message
            return True
        else:
            await self.irc.send_channel_message(
                channel,
                f"❌ Only administrators can stop the quiz"
            )
            return False

    async def handle_message(self, message: IRCMessage) -> None:
        if message.username and ('.' in message.username or '@' in message.username):
            return  # Ignore server messages

        if not message.content or not message.username or not message.channel:
            logger.debug(f"Skipping invalid message: {message}")
            return

        command, args = extract_command(message.content)
        self.logger.debug(f"Extracted command: {command}, args: {args}")
        
        if command in self.command_handlers:
            try:
                # Increase timeout for commands that send multiple messages
                timeout_duration = 45.0 if command == '!quiz' else 15.0
                async with asyncio.timeout(timeout_duration):
                    result = await self.command_handlers[command](message.username, message.channel)
                    # Consider command completed if it returns True or None
                    if result is True or result is None:
                        await asyncio.sleep(0.5)  # Small delay to ensure messages are sent
                        return
                    
            except asyncio.TimeoutError:
                logger.error(f"Command {command} timed out")
                await self.irc.send_channel_message(
                    message.channel,
                    "❌ Command timed out. Please try again."
                )
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}")
                await self.irc.send_channel_message(
                    message.channel,
                    "❌ Error executing command. Please try again."
                )
            return
            
        if (self.state.active and self.state.channel == message.channel
            and not message.content.startswith('!')):
            await self.handle_answer(message.username, message.content)

    async def cleanup(self):
        """Clean up resources when shutting down."""
        self._stopping = True
        
        # End any active game
        if self.state.active:
            try:
                await self.end_game()
            except Exception as e:
                self.logger.error(f"Error during game end in cleanup: {e}")
        
        # Collect remaining tasks
        remaining_tasks = set(t for t in self._tasks if not t.done())
        self._tasks.clear()
        
        # Cancel remaining tasks
        await self._cancel_tasks_safely(remaining_tasks)
        
        # Close connections
        try:
            await self.irc.disconnect()
        except Exception as e:
            self.logger.error(f"Error disconnecting IRC: {e}")
            
        try:
            await self.db.close()
        except Exception as e:
            self.logger.error(f"Error closing database: {e}")

    async def handle_answer(self, username: str, answer: str) -> None:
        if not username or not answer:
            logger.warning("Received answer with missing parameters")
            return
            
        try:
            async with self.lock:
                if not self.state.active or not self.state.current_question:
                    return
                    
                elapsed_time = self.state.get_elapsed_time()
                
                # Validate answer timing
                if elapsed_time < QUIZ_CONFIG.get('min_answer_time', 0.1):
                    logger.warning(f"Suspiciously fast answer from {username}: {elapsed_time}s")
                    return
                    
                if elapsed_time >= self.state.answer_timeout:
                    return

                # Process answer without timeout
                if is_answer_match(answer, self.state.current_answer):
                    base_points = calculate_base_points(
                        elapsed_time,
                        self.state.answer_timeout,
                        self.state.question_number
                    )
                    
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
                    try:
                        async with asyncio.timeout(5.0):  # Separate timeout for DB operation
                            await self.db.update_score(
                                username,
                                points,
                                elapsed_time,
                                self.score_tracker.streaks[username]
                            )
                    except asyncio.TimeoutError:
                        logger.error("Database update timed out")
                    
                    streak = self.score_tracker.streaks.get(username, 0)
                    streak_info = f" (Streak: {streak}x)" if streak > 1 else ""
                    
                    score_message = format_score_message(
                        username,
                        points,
                        base_points,
                        total_multiplier
                    ) + streak_info
                    
                    await self.irc.send_channel_message(self.state.channel, score_message)
                    
                    if self.state.fun_fact:
                        await self.irc.send_channel_message(
                            self.state.channel,
                            f"💡 {self.state.fun_fact}"
                        )
                    
                    # Cancel timeout task if it exists
                    if self.timeout_task and not self.timeout_task.done():
                        self.timeout_task.cancel()
                    
                    self.logger.debug(f"Question {self.state.question_number} completed")
                    
                    if self.state.question_number >= self.state.total_questions:
                        self.logger.info("All questions completed, ending game")
                        # Create a new task for ending game to avoid blocking
                        self._create_tracked_task(self.end_game(), "end_game")
                    else:
                        # Create a new task for next question
                        if self.state.active:
                            self.question_task = self._create_tracked_task(
                                self.next_question(),
                                f"question_task_{self.state.question_number + 1}"
                            )
                else:
                    self.score_tracker.reset_streak(username)

        except Exception as e:
            logger.error(f"Error processing answer: {e}")

    async def start_game(self, channel: str) -> bool:
        if not channel:
            logger.warning("Attempted to start game with no channel")
            return False
            
        async with self.lock:
            self.logger.debug(f"Game state before start: active={self.state.active}")
            if self.state.active:
                return False
                
            self.state = QuizState(
                active=True,
                channel=channel,
                total_questions=QUIZ_CONFIG['total_questions'],
                answer_timeout=QUIZ_CONFIG['answer_timeout']
            )
            self.score_tracker = ScoreTracker()
            
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
                await asyncio.sleep(0.1)  # Small delay between messages
            
            self.logger.debug(f"Game state after start: active={self.state.active}")
            self.question_task = self._create_tracked_task(
                self.next_question(),
                "question_task_1"
            )
            return True

    async def next_question(self) -> None:
        async with self.lock:
            if not self.state.active or self._stopping:
                self.logger.debug("Game inactive or stopping, skipping next question")
                return

            try:
                async with asyncio.timeout(45):
                    # Validate game state
                    if self.state.question_number >= self.state.total_questions:
                        self.logger.info("Maximum questions reached, ending game")
                        await self.end_game()
                        return

                    question = await self.mistral.get_trivia_question(self.state.used_questions)
                    if not question:
                        self.logger.warning("Using fallback question")
                        question = self.mistral._get_fallback_question()

                    if not question:
                        self.logger.error("Failed to get question, ending game")
                        await self.end_game()
                        return

                    self.state.question_number += 1
                    self.logger.debug(f"Processing question {self.state.question_number}")
                    
                    # Recheck after increment
                    if self.state.question_number > self.state.total_questions:
                        self.logger.info("Maximum questions reached after increment, ending game")
                        await self.end_game()
                        return

                    self.state.current_question = question[0]
                    self.state.current_answer = question[1]
                    self.state.fun_fact = question[2]
                    self.state.question_time = datetime.now()

                    # Use the state's add_used_question method instead of direct set manipulation
                    question_hash = f"{question[0]}:{question[1]}"
                    self.state.add_used_question(question_hash)

                    await self.irc.send_channel_message(
                        self.state.channel,
                        self.state.current_question,
                        question=True,
                        number=self.state.question_number
                    )

                    self.timeout_task = self._create_tracked_task(
                        self.handle_timeout(self.state.answer_timeout),
                        f"timeout_task_{self.state.question_number}"
                    )

            except asyncio.TimeoutError:
                logger.error("Question fetch timed out, using fallback")
                try:
                    question = self.mistral._get_fallback_question()
                    if question:
                        self.state.current_question = question[0]
                        self.state.current_answer = question[1]
                        self.state.fun_fact = question[2]
                        self.state.question_time = datetime.now()
                        
                        await self.irc.send_channel_message(
                            self.state.channel,
                            self.state.current_question,
                            question=True,
                            number=self.state.question_number
                        )
                        
                        self.timeout_task = self._create_tracked_task(
                            self.handle_timeout(self.state.answer_timeout),
                            f"timeout_task_{self.state.question_number}"
                        )
                    else:
                        logger.error("Failed to get fallback question, ending game")
                        await self.end_game()
                except Exception as e:
                    logger.error(f"Error processing fallback question: {e}")
                    await self.end_game()
            except Exception as e:
                logger.error(f"Error getting next question: {e}")
                await self.end_game()
