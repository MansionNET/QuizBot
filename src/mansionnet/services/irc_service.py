"""Service for handling IRC connections and messaging."""
import socket
import ssl
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass

from ..config.settings import IRC_CONFIG, IRC_FORMATTING

logger = logging.getLogger(__name__)

@dataclass
class IRCMessage:
    """Represents a parsed IRC message."""
    username: str
    channel: str
    content: str
    raw: str

class IRCService:
    """Handles IRC connection and messaging."""

    def __init__(self, message_handler: Optional[Callable] = None):
        """Initialize the IRC service."""
        self.server = IRC_CONFIG["server"]
        self.port = IRC_CONFIG["port"]
        self.nickname = IRC_CONFIG["nickname"]
        self.channels = IRC_CONFIG["channels"]
        self.message_handler = message_handler
        self.irc = None
        self.connected = False
        
        # Set up SSL context - exactly as in original
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def connect(self) -> bool:
        """Establish connection to the IRC server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.irc = self.ssl_context.wrap_socket(sock)
            
            logger.info(f"Connecting to {self.server}:{self.port}...")
            self.irc.connect((self.server, self.port))
            
            self.send(f"NICK {self.nickname}")
            self.send(f"USER {self.nickname} 0 * :MansionNet Quiz Bot")
            
            buffer = ""
            while True:
                data = self.irc.recv(2048).decode("UTF-8")
                buffer += data
                
                if "PING" in buffer:
                    ping_token = buffer[buffer.find("PING"):].split()[1]
                    self.send(f"PONG {ping_token}")
                
                if "001" in buffer:  # RPL_WELCOME
                    self.connected = True
                    logger.info("Successfully connected to IRC server!")
                    for channel in self.channels:
                        self.send(f"JOIN {channel}")
                        logger.info(f"Joined channel: {channel}")
                        time.sleep(1)
                    return True
                
                if "Closing Link" in buffer or "ERROR" in buffer:
                    return False
                    
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def send(self, message: str) -> bool:
        """Send a raw message to the IRC server."""
        try:
            if self.irc:
                self.irc.send(bytes(f"{message}\r\n", "UTF-8"))
                logger.debug(f"Sent: {message}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def send_channel_message(self, channel: str, message: str, **kwargs) -> bool:
        """Send a formatted message to a channel."""
        formatted_message = self.format_message(message, **kwargs)
        return self.send(f"PRIVMSG {channel} :{formatted_message}")

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
            
            return IRCMessage(
                username=username,
                channel=channel,
                content=content,
                raw=line
            )
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None

    def run(self):
        """Main IRC loop."""
        while True:
            try:
                if not self.connected and not self.connect():
                    logger.error("Failed to connect, retrying in 30 seconds...")
                    time.sleep(30)
                    continue
                
                buffer = ""
                while self.connected:
                    try:
                        data = self.irc.recv(2048).decode("UTF-8")
                        if not data:
                            self.connected = False
                            break
                            
                        buffer += data
                        lines = buffer.split("\r\n")
                        buffer = lines.pop()
                        
                        for line in lines:
                            logger.debug(f"Processing: {line}")
                            
                            if line.startswith("PING"):
                                self.send(f"PONG {line.split()[1]}")
                                continue
                                
                            message = self.parse_message(line)
                            if message and self.message_handler:
                                self.message_handler(message)
                                
                    except Exception as e:
                        logger.error(f"Error in message loop: {e}")
                        self.connected = False
                        break
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.connected = False
                time.sleep(30)
                continue