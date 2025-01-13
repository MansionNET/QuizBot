import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Set
import irc.client
from irc.client import ServerConnection
from game_manager import GameManager
from question_service import QuestionService
from database import Database
from config import BotConfig

logger = logging.getLogger(__name__)

class QuizBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.reactor = irc.client.Reactor()
        self.connection: Optional[ServerConnection] = None
        self.game_manager = GameManager(self)
        self.question_service = QuestionService(config.mistral_api_key)
        self.database = Database(config.database_url)
        self.command_handlers = {
            '!quiz': self.cmd_quiz,
            '!help': self.cmd_help,
            '!stats': self.cmd_stats,
            '!leaderboard': self.cmd_leaderboard,
            '!stop': self.cmd_stop
        }
        
    async def connect(self):
        """Connect to IRC server and join channels"""
        try:
            self.connection = self.reactor.server().connect(
                self.config.irc_server,
                self.config.irc_port,
                self.config.irc_nickname
            )
            
            self.connection.add_global_handler("welcome", self._on_connect)
            self.connection.add_global_handler("pubmsg", self._on_pubmsg)
            self.connection.add_global_handler("disconnect", self._on_disconnect)
            
            await self.database.connect()
            
        except irc.client.ServerConnectionError as e:
            logger.error(f"Error connecting to IRC server: {e}")
            raise

    async def start(self):
        """Start the bot's main loop"""
        while True:
            self.reactor.process_once(timeout=0.1)
            await asyncio.sleep(0.1)

    async def cleanup(self):
        """Cleanup resources before shutdown"""
        if self.connection and self.connection.is_connected():
            self.connection.disconnect("Bot shutting down")
        await self.database.disconnect()
        await self.game_manager.stop_all_games()

    def _on_connect(self, connection, event):
        """Handler for successful connection"""
        for channel in self.config.irc_channels:
            connection.join(channel)
            logger.info(f"Joined channel: {channel}")

    async def _on_pubmsg(self, connection, event):
        """Handler for public messages"""
        msg = event.arguments[0]
        if msg.startswith('!'):
            command = msg.split()[0].lower()
            if command in self.command_handlers:
                await self.command_handlers[command](event)

    def _on_disconnect(self, connection, event):
        """Handler for disconnection"""
        logger.warning("Disconnected from server")
        raise Exception("IRC Connection lost")

    async def send_message(self, channel: str, message: str):
        """Send a message to a channel"""
        if self.connection and self.connection.is_connected():
            self.connection.privmsg(channel, message)

    # Command handlers
    async def cmd_quiz(self, event):
        """Handle !quiz command"""
        channel = event.target
        nick = event.source.nick
        
        if not self.game_manager.is_game_active(channel):
            await self.game_manager.start_game(channel, nick)
        else:
            await self.send_message(channel, "A quiz game is already running!")

    async def cmd_help(self, event):
        """Handle !help command"""
        help_msg = (
            "🎮 Quiz Bot Commands:\n"
            "!quiz - Start a new quiz game\n"
            "!stats - Show your statistics\n"
            "!leaderboard - Show top players\n"
            "!help - Show this help message"
        )
        await self.send_message(event.target, help_msg)

    async def cmd_stats(self, event):
        """Handle !stats command"""
        stats = await self.database.get_player_stats(event.source.nick)
        if stats:
            msg = (
                f"📊 Stats for {event.source.nick}:\n"
                f"Total Score: {stats['total_score']}\n"
                f"Correct Answers: {stats['correct_answers']}\n"
                f"Best Streak: {stats['best_streak']}"
            )
        else:
            msg = f"No stats found for {event.source.nick}"
        await self.send_message(event.target, msg)

    async def cmd_leaderboard(self, event):
        """Handle !leaderboard command"""
        leaders = await self.database.get_leaderboard(limit=5)
        if leaders:
            msg = "🏆 Top Players:\n" + "\n".join(
                f"{i+1}. {player['nick']} - {player['total_score']} points"
                for i, player in enumerate(leaders)
            )
        else:
            msg = "No players on the leaderboard yet!"
        await self.send_message(event.target, msg)

    async def cmd_stop(self, event):
        """Handle !stop command"""
        if event.source.nick in self.config.admin_users:
            await self.game_manager.stop_game(event.target)
        else:
            await self.send_message(event.target, "Only admins can stop the game!")