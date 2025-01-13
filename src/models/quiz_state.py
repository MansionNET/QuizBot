"""Core quiz game state and logic."""
import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional

from models.question import QuestionManager
from models.database import Database
from services.irc_service import IRCService
from services.mistral_service import MistralService
from utils.scoring import ScoreTracker, calculate_base_points, calculate_streak_multiplier
from utils.scoring import calculate_speed_multiplier, calculate_final_score
from utils.text_processing import extract_command, is_answer_match

logger = logging.getLogger(__name__)

class QuizState:
    def __init__(
        self,
        mistral_service: MistralService,
        database: Database,
        irc_service: IRCService,
        admin_users: list,
        question_timeout: int = 30,
        questions_per_game: int = 10
    ):
        self.mistral_service = mistral_service
        self.database = database
        self.irc_service = irc_service
        self.admin_users = admin_users
        self.question_timeout = question_timeout
        self.questions_per_game = questions_per_game
        
        self.question_manager = QuestionManager(mistral_service)
        self.score_tracker = ScoreTracker()
        self.active_games: Dict[str, bool] = {}
        self.question_counts: Dict[str, int] = {}
        self.timeout_tasks: Dict[str, asyncio.Task] = {}
        
        # Register message handler
        self.irc_service.add_message_handler(self.handle_message)
        
        # Command handlers
        self.commands = {
            '!quiz': self.cmd_quiz,
            '!help': self.cmd_help,
            '!stats': self.cmd_stats,
            '!leaderboard': self.cmd_leaderboard,
            '!stop': self.cmd_stop
        }
        
    async def start(self):
        """Start the quiz state."""
        await self.database.connect()
        logger.info("Quiz state started")
        
    async def cleanup(self):
        """Cleanup resources."""
        for task in self.timeout_tasks.values():
            task.cancel()
        await self.database.disconnect()
        logger.info("Quiz state cleaned up")
        
    async def handle_message(self, channel: str, nick: str, message: str):
        """Handle incoming IRC messages."""
        command, args = extract_command(message)
        
        if command in self.commands:
            await self.commands[command](channel, nick, args)
        elif self.is_game_active(channel):
            await self.handle_answer(channel, nick, message)
            
    def is_game_active(self, channel: str) -> bool:
        """Check if a game is active in the channel."""
        return channel in self.active_games and self.active_games[channel]
        
    async def start_game(self, channel: str, starter: str):
        """Start a new quiz game."""
        if self.is_game_active(channel):
            await self.irc_service.send_message(channel, "A game is already in progress!")
            return
            
        self.active_games[channel] = True
        self.question_counts[channel] = 0
        welcome_msg = (
            "🎯 New Quiz Game Starting! | "
            f"Started by: {starter} | "
            f"Questions: {self.questions_per_game} | "
            "Get ready for the first question!"
        )
        await self.irc_service.send_message(channel, welcome_msg)
        await self.next_question(channel)
        
    async def next_question(self, channel: str):
        """Get and display the next question."""
        if not self.is_game_active(channel):
            return
            
        # Check if we've reached the question limit before trying to get a new one
        if self.question_counts[channel] >= self.questions_per_game:
            await self.stop_game(channel)
            return
            
        try:
            # Try to get next question
            question = await self.question_manager.get_next_question()
            if question:
                self.question_counts[channel] += 1  # Only increment if we got a question
                await self.irc_service.send_message(
                    channel,
                    f"Question {self.question_counts[channel]}/{self.questions_per_game}: {question.question}"
                )
                
                # Set timeout
                if channel in self.timeout_tasks:
                    self.timeout_tasks[channel].cancel()
                self.timeout_tasks[channel] = asyncio.create_task(
                    self.handle_timeout(channel)
                )
            else:
                logger.error("Failed to get next question")
                await self.irc_service.send_message(
                    channel,
                    "❌ Sorry, there was an error getting the next question. Ending game."
                )
                await self.stop_game(channel)
                
        except Exception as e:
            logger.error(f"Critical error in next_question: {e}")
            await self.irc_service.send_message(
                channel,
                "❌ An unexpected error occurred. Ending game."
            )
            await self.stop_game(channel)
            
    async def handle_answer(self, channel: str, nick: str, message: str):
        """Handle a potential answer."""
        if not self.is_game_active(channel):
            return
            
        current_question = self.question_manager.current_question
        if not current_question:
            return
            
        if is_answer_match(message, current_question.answer):
            # Calculate score
            answer_time = datetime.now()
            time_taken = (answer_time - current_question.asked_at).total_seconds()
            
            base_points = calculate_base_points()
            player_score = self.score_tracker.get_player_score(nick)
            
            speed_mult = calculate_speed_multiplier(time_taken, self.question_timeout)
            streak_mult = calculate_streak_multiplier(player_score.current_streak)
            final_points = calculate_final_score(base_points, streak_mult, speed_mult)
            
            # Update player stats
            player_score.total_score += final_points
            player_score.correct_answers += 1
            player_score.current_streak += 1
            player_score.best_streak = max(
                player_score.best_streak, player_score.current_streak
            )
            
            if not player_score.fastest_answer or time_taken < player_score.fastest_answer:
                player_score.fastest_answer = time_taken
            
            # Mark question as answered
            self.question_manager.mark_answered(nick)
            
            # Send success message
            await self.irc_service.send_message(
                channel,
                f"🎉 Correct, {nick}! +{final_points} points (streak: {player_score.current_streak}x) | "
                f"Fun fact: {current_question.fun_fact}"
            )
            
            # Cancel timeout task
            if channel in self.timeout_tasks:
                self.timeout_tasks[channel].cancel()
            
            # Move to next question
            await asyncio.sleep(3)
            await self.next_question(channel)
            
    async def handle_timeout(self, channel: str):
        """Handle question timeout."""
        await asyncio.sleep(self.question_timeout)
        
        if self.is_game_active(channel) and self.question_manager.current_question:
            await self.irc_service.send_message(
                channel,
                f"⏰ Time's up! The correct answer was: {self.question_manager.current_question.answer}"
            )
            
            # Reset all streaks
            for score in self.score_tracker.scores.values():
                score.current_streak = 0
                
            await asyncio.sleep(2)
            await self.next_question(channel)
            
    async def stop_game(self, channel: str):
        """Stop the current game."""
        if not self.is_game_active(channel):
            return
            
        self.active_games[channel] = False
        if channel in self.timeout_tasks:
            self.timeout_tasks[channel].cancel()
            del self.timeout_tasks[channel]
            
        # Clear question state
        self.question_manager.clear_used_questions()
            
        # Show final scores
        sorted_scores = sorted(
            self.score_tracker.scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True
        )
        
        if sorted_scores:
            message = "🏁 Final Scores: | " + " | ".join(
                f"{i+1}. {nick}: {score.total_score} points "
                f"({score.correct_answers} correct, best streak: {score.best_streak})"
                for i, (nick, score) in enumerate(sorted_scores[:5])
            )
        else:
            message = "Game ended with no scores!"
            
        await self.irc_service.send_message(channel, message)
        
        # Update database
        for nick, score in self.score_tracker.scores.items():
            await self.database.update_player_stats(
                nick=nick,
                score=score.total_score,
                correct_answers=score.correct_answers,
                best_streak=score.best_streak,
                answer_time=score.fastest_answer
            )
            
        # Clear game state
        self.score_tracker.scores.clear()
        if channel in self.question_counts:
            del self.question_counts[channel]
            
    async def cmd_quiz(self, channel: str, nick: str, args: str):
        """Handle !quiz command."""
        await self.start_game(channel, nick)
        
    async def cmd_help(self, channel: str, nick: str, args: str):
        """Handle !help command."""
        help_msg = (
            "🎮 Quiz Bot Commands: | "
            "!quiz - Start a new quiz game | "
            "!stats - Show your statistics | "
            "!leaderboard - Show top players | "
            "!help - Show this help message"
        )
        await self.irc_service.send_message(channel, help_msg)
        
    async def cmd_stats(self, channel: str, nick: str, args: str):
        """Handle !stats command."""
        stats = await self.database.get_player_stats(nick)
        if stats:
            time_str = ""
            if 'fastest_answer' in stats and stats['fastest_answer'] is not None:
                time_str = f", fastest answer: {stats['fastest_answer']:.1f}s"
                
            msg = (
                f"📊 Stats for {nick}: | "
                f"Total Score: {stats['total_score']} | "
                f"Correct Answers: {stats['correct_answers']} | "
                f"Best Streak: {stats['best_streak']}{time_str}"
            )
        else:
            msg = f"No stats found for {nick}"
        await self.irc_service.send_message(channel, msg)
        
    async def cmd_leaderboard(self, channel: str, nick: str, args: str):
        """Handle !leaderboard command."""
        leaders = await self.database.get_leaderboard(limit=5)
        if leaders:
            msg = "🏆 Top Players: | " + " | ".join(
                f"{i+1}. {player['nick']} - {player['total_score']} points"
                for i, player in enumerate(leaders)
            )
        else:
            msg = "No players on the leaderboard yet!"
        await self.irc_service.send_message(channel, msg)
        
    async def cmd_stop(self, channel: str, nick: str, args: str):
        """Handle !stop command."""
        if nick in self.admin_users:
            await self.stop_game(channel)
        else:
            await self.irc_service.send_message(
                channel,
                "Only admins can stop the game!"
            )
