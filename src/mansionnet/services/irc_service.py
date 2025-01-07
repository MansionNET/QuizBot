"""Service for handling IRC connections and messaging."""
import socket
import ssl
import time
import asyncio
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass
from asyncio import StreamReader, StreamWriter

from ..config.settings import IRC_CONFIG, IRC_FORMATTING

logger = logging.getLogger(__name__)

@dataclass
class IRCMessage:
    """Represents a parsed IRC message."""
    username: str
    channel: str
    content: str
    raw: str
    timestamp: float = time.time()

class IRCService:
    """Handles IRC connection and messaging."""

    def __init__(self, message_handler: Optional[Callable] = None):
        """Initialize the IRC service."""
        self.server = IRC_CONFIG["server"]
        self.port = IRC_CONFIG["port"]
        self.nickname = IRC_CONFIG["nickname"]
        self.channels = IRC_CONFIG.get("channels", ["#test_room"])
        self.message_handler = message_handler
        self.writer: Optional[StreamWriter] = None
        self.reader: Optional[StreamReader] = None
        self.connected = False
        self.last_pong = time.time()
        self.ping_timeout = 300  # 5 minutes
        self.message_timeout = 10  # 10 seconds for message sending
        self.connect_timeout = 30  # 30 seconds for connection
        self.reconnect_delay = 30
        self.lock = asyncio.Lock()
        self._tasks = set()
        
        # Set up SSL context
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
    def _create_tracked_task(self, coro, name=None):
        """Create and track an asyncio task."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def connect(self) -> bool:
        """Establish connection to the IRC server."""
        try:
            logger.info(f"Connecting to {self.server}:{self.port}...")
            
            async with asyncio.timeout(self.connect_timeout):
                # Connect using asyncio
                self.reader, self.writer = await asyncio.open_connection(
                    self.server, 
                    self.port,
                    ssl=self.ssl_context
                )
                
                # Send initial commands
                await self.send(f"NICK {self.nickname}")
                await self.send(f"USER {self.nickname} 0 * :MansionNet Quiz Bot")
                
                # Wait for welcome message
                while True:
                    line = await self.reader.readline()
                    if not line:
                        return False
                        
                    buffer = line.decode('utf-8', errors='ignore')
                    logger.debug(f"Received: {buffer.strip()}")
                    
                    if "PING" in buffer:
                        ping_token = buffer[buffer.find("PING"):].split()[1]
                        await self.send(f"PONG {ping_token}")
                        self.last_pong = time.time()
                    
                    if "001" in buffer:  # RPL_WELCOME
                        self.connected = True
                        logger.info("Successfully connected to IRC server!")
                        for channel in self.channels:
                            await self.send(f"JOIN {channel}")
                            logger.info(f"Joined channel: {channel}")
                            await asyncio.sleep(1)
                        return True
                    
                    if "ERROR" in buffer or "Closing Link" in buffer:
                        logger.error(f"Server returned error: {buffer}")
                        return False
                    
        except asyncio.TimeoutError:
            logger.error("Connection attempt timed out")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
        finally:
            if not self.connected and self.writer:
                self.writer.close()
                await self.writer.wait_closed()

    async def send(self, message: str) -> bool:
        """Send a raw message to the IRC server with timeout."""
        try:
            async with self.lock:
                async with asyncio.timeout(self.message_timeout):
                    if self.writer and not self.writer.is_closing():
                        self.writer.write(f"{message}\r\n".encode('utf-8'))
                        await self.writer.drain()
                        logger.debug(f"Sent: {message}")
                        return True
                    return False
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending message: {message[:50]}...")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.connected = False
            return False

    async def send_channel_message(self, channel: str, message: str, **kwargs) -> bool:
        """Send a formatted message to a channel with timeout."""
        try:
            formatted_message = self.format_message(message, **kwargs)
            async with asyncio.timeout(self.message_timeout):
                success = await self.send(f"PRIVMSG {channel} :{formatted_message}")
                if success:
                    logger.debug(f"Sent to {channel}: {formatted_message}")
                return success
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending channel message to {channel}: {message[:50]}...")
            return False
        except Exception as e:
            logger.error(f"Error sending channel message: {e}")
            return False

    def format_message(self, message: str, **kwargs) -> str:
        """Format a message with IRC color codes and styles."""
        fmt = IRC_FORMATTING
        formatted = message
        
        if kwargs.get('question'):
            formatted = (
                f"{fmt['COLOR']}{fmt['COLORS']['ORANGE']},{fmt['COLORS']['BLACK']}"
                f"{fmt['BOLD']}Question {kwargs['number']}/10:{fmt['RESET']} "
                f"{formatted}"
            )
        elif kwargs.get('correct'):
            formatted = f"✨ {formatted}"
        elif kwargs.get('timeout'):
            formatted = f"⏰ {formatted}"
        elif kwargs.get('announcement'):
            formatted = (
                f"{fmt['COLOR']}{fmt['COLORS']['ORANGE']},{fmt['COLORS']['BLACK']}"
                f"{fmt['BOLD']}{formatted}{fmt['RESET']}"
            )
            
        return formatted

    def parse_message(self, line: str) -> Optional[IRCMessage]:
        """Parse an IRC message into its components."""
        try:
            if "PRIVMSG" not in line:
                return None
                
            parts = line.split("PRIVMSG", 1)[1].split(":", 1)
            if len(parts) != 2:
                return None
                
            channel = parts[0].strip()
            content = parts[1].strip()
            username = line[1:].split("!")[0]
            
            # Log parsed message for debugging
            logger.debug(f"Parsed message - User: {username}, Channel: {channel}, Content: {content}")
            
            return IRCMessage(
                username=username,
                channel=channel,
                content=content,
                raw=line,
                timestamp=time.time()
            )
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None

    async def process_messages(self) -> None:
        """Process incoming messages."""
        while True:
            try:
                if not self.reader:
                    return
                    
                line = await self.reader.readline()
                if not line:
                    logger.error("Server closed connection")
                    self.connected = False
                    return
                    
                decoded_line = line.decode('utf-8', errors='ignore').strip()
                logger.debug(f"Processing: {decoded_line}")
                
                if decoded_line.startswith("PING"):
                    await self.send(f"PONG {decoded_line.split()[1]}")
                    self.last_pong = time.time()
                    continue
                    
                message = self.parse_message(decoded_line)
                if message and self.message_handler:
                    try:
                        await self.message_handler(message)
                    except Exception as e:
                        logger.error(f"Error in message handler: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error in message processing: {e}")
                self.connected = False
                return

    async def keep_alive(self) -> None:
        """Keep the connection alive by checking ping responses."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if time.time() - self.last_pong > self.ping_timeout:
                    logger.error("Ping timeout")
                    self.connected = False
                    return
                    
                if self.connected and self.writer and not self.writer.is_closing():
                    await self.send(f"PING :{self.server}")
            except Exception as e:
                logger.error(f"Error in keep_alive: {e}")
                self.connected = False
                return

    async def run(self) -> None:
        """Main IRC loop."""
        while True:
            try:
                if not self.connected:
                    logger.info("Attempting to (re)connect...")
                    if not await self.connect():
                        logger.error("Failed to connect, retrying...")
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                    
                    # Start message processing and keepalive tasks
                    message_task = self._create_tracked_task(
                        self.process_messages(),
                        "message_processor"
                    )
                    keepalive_task = self._create_tracked_task(
                        self.keep_alive(),
                        "keepalive"
                    )
                    
                    try:
                        # Wait for either task to complete
                        done, pending = await asyncio.wait(
                            [message_task, keepalive_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel remaining tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                    except Exception as e:
                        logger.error(f"Error in task handling: {e}")
                    finally:
                        # Clean up
                        self.connected = False
                        if self.writer:
                            try:
                                self.writer.close()
                                await self.writer.wait_closed()
                            except Exception as e:
                                logger.error(f"Error closing writer: {e}")
                                
                await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.connected = False
                await asyncio.sleep(self.reconnect_delay)

    async def disconnect(self) -> None:
        """Gracefully disconnect from the IRC server."""
        logger.info("Disconnecting from IRC server...")
        
        # Cancel all tracked tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            try:
                async with asyncio.timeout(5.0):
                    await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for tasks to cancel")
        
        # Send QUIT command if still connected
        if self.connected and self.writer and not self.writer.is_closing():
            try:
                await self.send("QUIT :Bot shutting down")
            except Exception as e:
                logger.error(f"Error sending QUIT command: {e}")
        
        # Close the writer
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing writer: {e}")
        
        self.connected = False
        logger.info("Disconnected from IRC server")