"""Service for handling IRC connections and messaging."""
import socket
import ssl
import time
import asyncio
import logging
from typing import Optional, Callable, Any, Set
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
        
        # Connection state
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.connected = False
        self._stopping = False
        
        # Timing configuration
        self.last_pong = time.time()
        self.ping_timeout = IRC_CONFIG.get("ping_timeout", 600)
        self.message_timeout = IRC_CONFIG.get("message_timeout", 30)
        self.connect_timeout = IRC_CONFIG.get("connect_timeout", 60)
        self.reconnect_delay = IRC_CONFIG.get("reconnect_delay", 30)
        self.max_reconnect_attempts = IRC_CONFIG.get("max_reconnect_attempts", 3)
        
        # Synchronization and tracking
        self.lock = asyncio.Lock()
        self._tasks: Set[asyncio.Task] = set()
        self._message_buffer = []
        self._buffer_size = IRC_CONFIG.get("buffer_size", 10)
        self._last_message_time = time.time()
        self._message_rate_limit = IRC_CONFIG.get("message_rate_limit", 1.0)
        
        # Set up SSL context with proper error handling
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create a properly configured SSL context."""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            # Enable all available protocols
            ctx.options |= ssl.OP_ALL
            # Set better cipher preferences
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            # Add additional options for better compatibility
            ctx.options |= ssl.OP_NO_SSLv2
            ctx.options |= ssl.OP_NO_SSLv3
            return ctx
        except Exception as e:
            logger.error(f"Error creating SSL context: {e}")
            # Fall back to basic SSL context if needed
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        
    def _create_tracked_task(self, coro, name=None) -> Optional[asyncio.Task]:
        """Create and track an asyncio task."""
        if self._stopping:
            return None
            
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        
        def cleanup_task(t):
            self._tasks.discard(t)
            if not self._stopping:
                try:
                    exc = t.exception()
                    if exc and not isinstance(exc, asyncio.CancelledError):
                        logger.error(f"Task {t.get_name()} failed: {exc}")
                except (asyncio.CancelledError, RuntimeError):
                    pass
                
        task.add_done_callback(cleanup_task)
        return task

    async def _handle_ssl_error(self, e: ssl.SSLError) -> bool:
        """Handle SSL-specific errors with proper recovery."""
        error_str = str(e)
        
        # Don't log close notify errors during shutdown
        if 'APPLICATION_DATA_AFTER_CLOSE_NOTIFY' in error_str:
            if not self._stopping:
                logger.debug("Ignoring harmless SSL close notify error")
            return True
            
        if 'WRONG_VERSION_NUMBER' in error_str:
            logger.warning("SSL version mismatch, attempting with different protocol")
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE
            return True
            
        if 'SSLV3_ALERT_CERTIFICATE_UNKNOWN' in error_str:
            logger.warning("Certificate validation failed, continuing with reduced security")
            self.ssl_context.check_hostname = False
            return True
            
        if not self._stopping:
            logger.error(f"Unhandled SSL error: {e}")
        return False

    async def connect(self) -> bool:
        """Establish connection to the IRC server with improved error handling."""
        attempt = 0
        while attempt < self.max_reconnect_attempts and not self._stopping:
            try:
                logger.info(f"Connecting to {self.server}:{self.port}... (Attempt {attempt + 1}/{self.max_reconnect_attempts})")
                
                async with asyncio.timeout(self.connect_timeout):
                    # Clean up any existing connection
                    await self._cleanup_connection()
                    
                    # Establish new connection
                    self.reader, self.writer = await asyncio.open_connection(
                        self.server, 
                        self.port,
                        ssl=self.ssl_context
                    )
                    
                    # Send initial commands
                    await self.send(f"NICK {self.nickname}")
                    await self.send(f"USER {self.nickname} 0 * :MansionNet Quiz Bot")
                    
                    # Wait for welcome message
                    async for line in self._read_lines():
                        if "001" in line:  # RPL_WELCOME
                            self.connected = True
                            logger.info("Successfully connected to IRC server!")
                            # Join channels with delay to prevent flood
                            for channel in self.channels:
                                await self.send(f"JOIN {channel}")
                                logger.info(f"Joined channel: {channel}")
                                await asyncio.sleep(1)
                            return True
                            
                        if "ERROR" in line or "Closing Link" in line:
                            raise ConnectionError(f"Server returned error: {line}")
                            
                        if "PING" in line:
                            ping_token = line[line.find("PING"):].split()[1]
                            await self.send(f"PONG {ping_token}")
                            self.last_pong = time.time()
                    
            except ssl.SSLError as e:
                if await self._handle_ssl_error(e):
                    attempt += 1
                    continue
                logger.error("Unrecoverable SSL error")
                return False
                
            except asyncio.TimeoutError:
                logger.error(f"Connection attempt {attempt + 1} timed out")
                
            except Exception as e:
                logger.error(f"Connection error on attempt {attempt + 1}: {e}")
                
            attempt += 1
            if attempt < self.max_reconnect_attempts and not self._stopping:
                await asyncio.sleep(self.reconnect_delay)
                
        return False

    async def _cleanup_connection(self):
        """Clean up existing connection."""
        if not self.writer:
            return
            
        try:
            if not self.writer.is_closing():
                # Set a flag to prevent further writes
                transport = self.writer.transport
                if transport:
                    transport.abort()  # Force close the transport
                    
                # Don't wait for clean close during shutdown
                if not self._stopping:
                    try:
                        async with asyncio.timeout(1.0):
                            await self.writer.wait_closed()
                    except (asyncio.TimeoutError, Exception) as e:
                        if not self._stopping:
                            logger.debug(f"Error waiting for writer close (ignorable): {e}")
        except Exception as e:
            if not self._stopping:
                logger.debug(f"Error during connection cleanup: {e}")
        finally:
            self.writer = None
            self.reader = None
            self.connected = False

    async def _read_lines(self):
        """Safely read lines from the IRC server."""
        while self.reader and not self.reader.at_eof() and not self._stopping:
            try:
                line = await self.reader.readline()
                if not line:
                    break
                yield line.decode('utf-8', errors='ignore').strip()
            except ssl.SSLError as e:
                if not await self._handle_ssl_error(e):
                    break
            except Exception as e:
                if not self._stopping:
                    logger.debug(f"Error reading line: {e}")
                break

    async def send(self, message: str) -> bool:
        """Send a raw message to the IRC server with improved handling."""
        if not message or not self.writer or self._stopping:
            return False
            
        try:
            async with self.lock:
                # Rate limiting
                now = time.time()
                if now - self._last_message_time < self._message_rate_limit:
                    await asyncio.sleep(self._message_rate_limit - (now - self._last_message_time))
                
                async with asyncio.timeout(self.message_timeout):
                    if self.writer.is_closing():
                        return False
                        
                    try:
                        self.writer.write(f"{message}\r\n".encode('utf-8'))
                        await self.writer.drain()
                        self._last_message_time = time.time()
                        logger.debug(f"Sent: {message}")
                        return True
                    except ssl.SSLError as e:
                        if not await self._handle_ssl_error(e):
                            raise
                        return False
                        
        except asyncio.TimeoutError:
            if not self._stopping:
                logger.error(f"Timeout sending message: {message[:50]}...")
        except Exception as e:
            if not self._stopping:
                logger.error(f"Error sending message: {e}")
            self.connected = False
            
        return False

    async def send_channel_message(self, channel: str, message: str, **kwargs) -> bool:
        """Send a formatted message to a channel with retries."""
        if self._stopping:
            return False
            
        retries = 2
        while retries > 0 and not self._stopping:
            try:
                formatted_message = self.format_message(message, **kwargs)
                
                # Buffer messages if sending too fast
                if self._message_buffer:
                    if len(self._message_buffer) >= self._buffer_size:
                        self._message_buffer.pop(0)
                    self._message_buffer.append((channel, formatted_message))
                    await asyncio.sleep(0.5)
                
                async with asyncio.timeout(self.message_timeout):
                    success = await self.send(f"PRIVMSG {channel} :{formatted_message}")
                    if success:
                        logger.debug(f"Sent to {channel}: {formatted_message}")
                        return True
                    
            except asyncio.TimeoutError:
                if not self._stopping:
                    logger.error(f"Timeout sending channel message to {channel}: {message[:50]}...")
            except Exception as e:
                if not self._stopping:
                    logger.error(f"Error sending channel message: {e}")
            
            retries -= 1
            if retries > 0 and not self._stopping:
                await asyncio.sleep(1)
                
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
        """Parse an IRC message into its components with improved error handling."""
        try:
            if "PRIVMSG" not in line:
                return None
                
            if line.count(":") < 2:
                return None
                
            parts = line.split("PRIVMSG", 1)[1].split(":", 1)
            if len(parts) != 2:
                return None
                
            channel = parts[0].strip()
            content = parts[1].strip()
            
            # More robust username extraction
            username = ""
            if line.startswith(":") and "!" in line:
                username = line[1:].split("!", 1)[0]
            
            if not username or not channel or not content:
                return None
                
            logger.debug(f"Parsed message - User: {username}, Channel: {channel}, Content: {content}")
            
            return IRCMessage(
                username=username,
                channel=channel,
                content=content,
                raw=line,
                timestamp=time.time()
            )
        except Exception as e:
            if not self._stopping:
                logger.error(f"Error parsing message: {e}")
            return None

    async def process_messages(self) -> None:
        """Process incoming messages with improved error handling."""
        while not self._stopping:
            try:
                if not self.reader:
                    return
                    
                async for line in self._read_lines():
                    if self._stopping:
                        return
                        
                    if line.startswith("PING"):
                        await self.send(f"PONG {line.split()[1]}")
                        self.last_pong = time.time()
                        continue
                        
                    message = self.parse_message(line)
                    if message and self.message_handler:
                        try:
                            await self.message_handler(message)
                        except Exception as e:
                            if not self._stopping:
                                logger.error(f"Error in message handler: {e}")
                            
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._stopping:
                    logger.error(f"Error in message processing: {e}")
                    self.connected = False
                    return

    async def keep_alive(self) -> None:
        """Keep the connection alive with improved ping/pong tracking."""
        while not self._stopping:
            try:
                await asyncio.sleep(30)
                
                if self._stopping:
                    return
                    
                if time.time() - self.last_pong > self.ping_timeout:
                    logger.error("Ping timeout - no response from server")
                    self.connected = False
                    return
                    
                if self.connected and self.writer and not self.writer.is_closing():
                    await self.send(f"PING :{self.server}")
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._stopping:
                    logger.error(f"Error in keep_alive: {e}")
                    self.connected = False
                    return

    async def run(self) -> None:
        """Main IRC loop with improved connection management."""
        reconnect_attempts = 0
        
        while not self._stopping:
            try:
                if not self.connected:
                    logger.info("Attempting to (re)connect...")
                    if not await self.connect():
                        reconnect_attempts += 1
                        if reconnect_attempts >= self.max_reconnect_attempts:
                            logger.error("Max reconnection attempts reached")
                            return
                        logger.error("Failed to connect, retrying...")
                        await asyncio.sleep(self.reconnect_delay)
                        continue
                    
                    reconnect_attempts = 0  # Reset counter on successful connection
                    
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
                        if message_task and keepalive_task:
                            done, pending = await asyncio.wait(
                                [message_task, keepalive_task],
                                return_when=asyncio.FIRST_COMPLETED
                            )
                            
                            # Cancel remaining tasks
                            for task in pending:
                                task.cancel()
                                try:
                                    await task
                                except (asyncio.CancelledError, Exception):
                                    pass
                    except Exception as e:
                        if not self._stopping:
                            logger.error(f"Error in task handling: {e}")
                    finally:
                        # Clean up if not stopping
                        if not self._stopping:
                            self.connected = False
                            await self._cleanup_connection()
                                
                await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._stopping:
                    logger.error(f"Error in main loop: {e}")
                    self.connected = False
                    await asyncio.sleep(self.reconnect_delay)

    async def disconnect(self) -> None:
        """Gracefully disconnect from the IRC server."""
        if self._stopping:
            return
            
        logger.info("Disconnecting from IRC server...")
        self._stopping = True
        
        # Cancel all tracked tasks first
        tasks_to_cancel = [t for t in self._tasks if not t.done()]
        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()
            
            try:
                async with asyncio.timeout(1.0):  # Reduced timeout
                    await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore timeout during shutdown
        
        # Force cleanup immediately
        await self._cleanup_connection()
        logger.info("Disconnected from IRC server")