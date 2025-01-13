"""IRC service for bot communication."""
import logging
import asyncio
import ssl
import re
from typing import List, Optional, Callable, Awaitable
from dataclasses import dataclass
import irc.client
from irc.connection import Factory
from irc.client import ServerConnection, Event

logger = logging.getLogger(__name__)

class IRCService:
    """Service for handling IRC communication."""
    
    def __init__(
        self,
        server: str,
        port: int = 6697,
        nickname: str = "QuizBot",
        channels: List[str] = None,
        reconnect_delay: int = 30,
        use_ssl: bool = True
    ):
        self.server = server
        self.port = port
        self.nickname = nickname
        self.channels = channels or ["#quizbot"]
        self.reconnect_delay = reconnect_delay
        self.use_ssl = use_ssl
        
        self.reactor = irc.client.Reactor()
        self.connection: Optional[ServerConnection] = None
        self.message_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None
        self.connected = False
        self.reconnect_task: Optional[asyncio.Task] = None
        self._event_loop = None
        
        # Configure connection timeouts
        self.reactor.scheduler.tick_period = 0.1
        irc.client.ServerConnection.buffer_class.errors = 'replace'
        
    def add_message_handler(
        self,
        handler: Callable[[str, str, str], Awaitable[None]]
    ):
        """Add a handler for incoming messages."""
        self.message_callback = handler
        
    def _format_irc_message(self, message: str) -> List[str]:
        """Format a message for IRC by handling newlines and long messages."""
        # Replace newlines with a separator
        message = message.replace('\n', ' | ')
        
        # Clean up any double spaces or separators
        message = re.sub(r'\s+\|\s+', ' | ', message)
        message = re.sub(r'\s{2,}', ' ', message)
        
        # Split long messages
        max_length = 400
        messages = []
        for i in range(0, len(message), max_length):
            part = message[i:i + max_length]
            if part:
                messages.append(part)
                
        return messages
        
    async def connect(self):
        """Connect to IRC server and join channels."""
        try:
            self._event_loop = asyncio.get_running_loop()
            
            # Set up SSL if enabled
            if self.use_ssl:
                ssl_context = ssl.create_default_context()
                connect_factory = Factory(wrapper=lambda sock: ssl_context.wrap_socket(sock,
                                                                                    server_hostname=self.server))
            else:
                connect_factory = Factory()
            
            self.connection = self.reactor.server().connect(
                self.server,
                self.port,
                self.nickname,
                connect_factory=connect_factory
            )
            
            # Set up event handlers
            self.connection.add_global_handler("welcome", self._on_connect)
            self.connection.add_global_handler("pubmsg", self._handle_pubmsg)
            self.connection.add_global_handler("disconnect", self._on_disconnect)
            self.connection.add_global_handler("error", self._on_error)
            self.connection.add_global_handler("join", self._on_join)
            self.connection.add_global_handler("nick", self._on_nick_change)
            
            logger.info(f"Connecting to {self.server}:{self.port} as {self.nickname} "
                       f"{'with SSL' if self.use_ssl else 'without SSL'}")
            
        except irc.client.ServerConnectionError as e:
            logger.error(f"Error connecting to IRC server: {e}")
            await self._handle_connection_error()
            
    def _on_connect(self, connection: ServerConnection, event: Event):
        """Handler for successful connection."""
        self.connected = True
        logger.info("Successfully connected to IRC server")
        
        # Join all channels
        for channel in self.channels:
            connection.join(channel)
            logger.info(f"Joining channel: {channel}")
            
    def _on_join(self, connection: ServerConnection, event: Event):
        """Handler for successful channel join."""
        logger.info(f"Successfully joined channel: {event.target}")
            
    def _handle_pubmsg(self, connection: ServerConnection, event: Event):
        """Handle public messages by scheduling them in the event loop."""
        if self.message_callback and self._event_loop:
            self._event_loop.create_task(
                self.message_callback(
                    event.target,
                    event.source.nick,
                    event.arguments[0]
                )
            )
                
    def _on_disconnect(self, connection: ServerConnection, event: Event):
        """Handler for disconnection."""
        self.connected = False
        logger.warning("Disconnected from IRC server")
        if self._event_loop:
            self._event_loop.create_task(self._handle_disconnect())
            
    async def _handle_disconnect(self):
        """Handle disconnection in async context."""
        self._schedule_reconnect()
        
    def _on_error(self, connection: ServerConnection, event: Event):
        """Handler for IRC errors."""
        logger.error(f"IRC Error: {event.arguments[0] if event.arguments else 'Unknown error'}")
        
    def _on_nick_change(self, connection: ServerConnection, event: Event):
        """Handler for nickname changes."""
        if event.source.nick == self.nickname:
            self.nickname = event.target
            logger.info(f"Nickname changed to: {self.nickname}")
            
    def _schedule_reconnect(self):
        """Schedule a reconnection attempt."""
        if self._event_loop and (not self.reconnect_task or self.reconnect_task.done()):
            self.reconnect_task = self._event_loop.create_task(self._reconnect())
            
    async def _reconnect(self):
        """Attempt to reconnect to the IRC server."""
        while not self.connected:
            logger.info(f"Attempting to reconnect in {self.reconnect_delay} seconds...")
            await asyncio.sleep(self.reconnect_delay)
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {e}")
                
    async def _handle_connection_error(self):
        """Handle initial connection errors."""
        logger.error("Failed to connect to IRC server")
        self._schedule_reconnect()
        
    async def send_message(self, channel: str, message: str):
        """Send a message to a channel."""
        if self.connected and self.connection:
            try:
                # Format message for IRC
                messages = self._format_irc_message(message)
                
                for msg in messages:
                    self.connection.privmsg(channel, msg)
                    # Small delay between messages to avoid flooding
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error sending message to {channel}: {e}")
        else:
            logger.warning(f"Cannot send message to {channel}: Not connected")
            
    async def process(self):
        """Process IRC events."""
        self.reactor.process_once(timeout=0.1)
        await asyncio.sleep(0.1)
        
    async def disconnect(self):
        """Disconnect from the IRC server."""
        if self.connection and self.connection.is_connected():
            try:
                for channel in self.channels:
                    self.connection.part(channel, "Bot shutting down")
                self.connection.quit("Bot shutting down")
                self.connected = False
                logger.info("Disconnected from IRC server")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
                
    def is_connected(self) -> bool:
        """Check if connected to IRC server."""
        return self.connected and self.connection and self.connection.is_connected()