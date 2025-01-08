"""Command handler wrapper with proper timeout handling."""
from typing import Callable, Awaitable, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

async def execute_command_with_timeout(
    command_func: Callable[[str, str], Awaitable[Any]],
    username: str,
    channel: str,
    irc_service: Any,
    timeout_duration: float = 5.0
) -> bool:
    """
    Execute a command with timeout handling.
    Returns True if command completed successfully, False otherwise.
    """
    command_completed = False
    try:
        async with asyncio.timeout(timeout_duration):
            await command_func(username, channel)
            command_completed = True
    except asyncio.TimeoutError:
        if not command_completed:
            logger.error(f"Command timed out after {timeout_duration}s")
            await irc_service.send_channel_message(
                channel,
                "❌ Command timed out. Please try again."
            )
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        await irc_service.send_channel_message(
            channel,
            "❌ Error executing command. Please try again."
        )
    
    return command_completed