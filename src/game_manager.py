import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class PlayerState:
    score: int = 0
    streak: int = 0
    correct_answers: int = 0
    last_answer_time: Optional[datetime] = None
    best_streak: int = 0

@dataclass
class GameState:
    channel: str
    starter: str
    players: Dict[str, PlayerState] = field(default_factory=dict)
    current_question: Optional[dict] = None
    question_start_time: Optional[datetime] = None
    question_number: int = 0
    active: bool = True
    used_questions: Set[str] = field(default_factory=set)
    timeout_task: Optional[asyncio.Task] = None

class GameManager:
    def __init__(self, bot):
        self.bot = bot
        self.games: Dict[str, GameState] = {}
        
    def is_game_active(self, channel: str) -> bool:
        """Check if a game is active in the given channel"""
        return channel in self.games and self.games[channel].active

    async def start_game(self, channel: str, starter: str):
        """Start a new quiz game in the channel"""
        if channel in self.games:
            await self.stop_game(channel)
            
        self.games[channel] = GameState(channel=channel, starter=starter)
        
        welcome_msg = (
            "🎯 New Quiz Game Starting!\n"
            f"Started by: {starter}\n"
            f"Questions: {self.bot.config.questions_per_game}\n"
            "Get ready for the first question!"
        )
        await self.bot.send_message(channel, welcome_msg)
        await self.next_question(channel)

    async def stop_game(self, channel: str):
        """Stop the current game in the channel"""
        if channel in self.games:
            game = self.games[channel]
            game.active = False
            
            if game.timeout_task:
                game.timeout_task.cancel()
                
            # Show final scores
            await self.show_final_scores(channel)
            # Update database with game results
            await self.update_database(channel)
            # Clean up game state
            del self.games[channel]

    async def next_question(self, channel: str):
        """Get and display the next question"""
        game = self.games.get(channel)
        if not game or not game.active:
            return

        game.question_number += 1
        if game.question_number > self.bot.config.questions_per_game:
            await self.stop_game(channel)
            return

        try:
            # Get a question that hasn't been used in this game
            question = await self.bot.question_service.generate_question(game.used_questions)
            if not question:
                logger.error("Failed to get a unique question")
                await self.bot.send_message(
                    channel,
                    "Sorry, there was an error getting the question. Ending game..."
                )
                await self.stop_game(channel)
                return
                
            game.used_questions.add(question["id"])
            game.current_question = question
            game.question_start_time = datetime.now()
            
            # Display question
            await self.bot.send_message(
                channel,
                f"Question {game.question_number}/{self.bot.config.questions_per_game}:\n"
                f"{question['question']}"
            )
            
            # Set timeout
            if game.timeout_task:
                game.timeout_task.cancel()
            game.timeout_task = asyncio.create_task(
                self.question_timeout(channel)
            )
            
        except Exception as e:
            logger.error(f"Error getting question: {e}")
            await self.bot.send_message(
                channel,
                "Sorry, there was an error getting the question. Ending game..."
            )
            await self.stop_game(channel)

    async def handle_answer(self, channel: str, nick: str, answer: str):
        """Process a player's answer"""
        game = self.games.get(channel)
        if not game or not game.current_question:
            return

        # Initialize player state if needed
        if nick not in game.players:
            game.players[nick] = PlayerState()

        player = game.players[nick]
        now = datetime.now()
        
        # Anti-cheat: Check minimum answer time
        if (player.last_answer_time and 
            (now - player.last_answer_time).total_seconds() < self.bot.config.min_answer_time):
            return

        player.last_answer_time = now

        # Check answer
        if self.check_answer(answer, game.current_question['answer']):
            # Calculate points
            time_taken = (now - game.question_start_time).total_seconds()
            points = self.calculate_points(time_taken, player.streak)
            
            # Update player stats
            player.score += points
            player.streak += 1
            player.correct_answers += 1
            player.best_streak = max(player.best_streak, player.streak)
            
            # Cancel timeout task
            if game.timeout_task:
                game.timeout_task.cancel()
            
            # Send success message
            await self.bot.send_message(
                channel,
                f"🎉 Correct, {nick}! +{points} points "
                f"(streak: {player.streak}x)\n"
                f"Fun fact: {game.current_question['fun_fact']}"
            )
            
            # Move to next question
            await asyncio.sleep(3)  # Give time to read fun fact
            await self.next_question(channel)
        
        # No else needed - wrong answers are ignored

    def check_answer(self, given_answer: str, correct_answer: str) -> bool:
        """Check if the given answer matches the correct answer"""
        return given_answer.lower().strip() == correct_answer.lower().strip()

    def calculate_points(self, time_taken: float, streak: int) -> int:
        """Calculate points based on answer speed and streak"""
        # Base points
        points = self.bot.config.base_points
        
        # Speed multiplier (faster = more points)
        max_time = self.bot.config.question_timeout
        speed_multiplier = max(
            1.0,
            self.bot.config.speed_multiplier_max * (1 - time_taken / max_time)
        )
        
        # Streak multiplier (consecutive correct answers)
        streak_multiplier = min(1 + (streak * 0.1), 2.0)  # Max 2x from streak
        
        return int(points * speed_multiplier * streak_multiplier)

    async def question_timeout(self, channel: str):
        """Handler for question timeout"""
        await asyncio.sleep(self.bot.config.question_timeout)
        
        game = self.games.get(channel)
        if game and game.active and game.current_question:
            await self.bot.send_message(
                channel,
                f"⏰ Time's up! The correct answer was: {game.current_question['answer']}"
            )
            
            # Reset all players' streaks
            for player in game.players.values():
                player.streak = 0
            
            await asyncio.sleep(2)
            await self.next_question(channel)

    async def show_final_scores(self, channel: str):
        """Display final scores at the end of the game"""
        game = self.games.get(channel)
        if not game:
            return
            
        # Sort players by score
        sorted_players = sorted(
            game.players.items(),
            key=lambda x: x[1].score,
            reverse=True
        )
        
        if not sorted_players:
            await self.bot.send_message(channel, "Game ended with no scores!")
            return
            
        message = "🏁 Final Scores:\n" + "\n".join(
            f"{i+1}. {nick}: {player.score} points "
            f"({player.correct_answers} correct, best streak: {player.best_streak})"
            for i, (nick, player) in enumerate(sorted_players[:5])
        )
        
        await self.bot.send_message(channel, message)

    async def update_database(self, channel: str):
        """Update the database with game results"""
        game = self.games.get(channel)
        if not game:
            return
            
        for nick, player in game.players.items():
            await self.bot.database.update_player_stats(
                nick=nick,
                score=player.score,
                correct_answers=player.correct_answers,
                best_streak=player.best_streak
            )

    async def stop_all_games(self):
        """Stop all active games (used during shutdown)"""
        channels = list(self.games.keys())
        for channel in channels:
            await self.stop_game(channel)
