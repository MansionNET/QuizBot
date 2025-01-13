"""Text processing utilities for the quiz bot."""
import re
import logging
from typing import Tuple, List
from difflib import SequenceMatcher
import unicodedata

logger = logging.getLogger(__name__)

def extract_command(message: str) -> Tuple[str, str]:
    """Extract command and arguments from a message.
    
    Args:
        message: Raw message text
        
    Returns:
        Tuple[str, str]: Command and remaining arguments
    """
    parts = message.strip().split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return command, args

def normalize_text(text: str) -> str:
    """Normalize text for comparison.
    
    Args:
        text: Text to normalize
        
    Returns:
        str: Normalized text
    """
    # Convert to lowercase and strip whitespace
    text = text.lower().strip()
    
    # Remove accents and convert to ASCII
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode()
    
    # Remove punctuation and extra whitespace
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    
    return text

def is_answer_match(
    given: str,
    correct: str,
    similarity_threshold: float = 0.85
) -> bool:
    """Check if a given answer matches the correct answer.
    
    Args:
        given: User's answer
        correct: Correct answer
        similarity_threshold: Minimum similarity ratio for fuzzy matching
        
    Returns:
        bool: True if answer matches, False otherwise
    """
    # Normalize both texts
    given = normalize_text(given)
    correct = normalize_text(correct)
    
    # Direct match
    if given == correct:
        return True
        
    # Check if correct answer contains the given answer
    if len(given) >= 4 and given in correct:
        return True
        
    # For longer answers, use fuzzy matching
    if len(correct) > 5:
        similarity = SequenceMatcher(None, given, correct).ratio()
        return similarity >= similarity_threshold
        
    return False

def split_message(
    message: str,
    max_length: int = 400,
    separator: str = " "
) -> List[str]:
    """Split a long message into IRC-friendly chunks.
    
    Args:
        message: Message to split
        max_length: Maximum length for each chunk
        separator: Character to split on
        
    Returns:
        List[str]: List of message chunks
    """
    if len(message) <= max_length:
        return [message]
        
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in message.split(separator):
        word_length = len(word) + 1  # +1 for the separator
        
        if current_length + word_length > max_length:
            if current_chunk:
                chunks.append(separator.join(current_chunk))
                current_chunk = [word]
                current_length = word_length
            else:
                # Word is longer than max_length, need to split it
                chunks.append(word[:max_length])
                if len(word) > max_length:
                    current_chunk = [word[max_length:]]
                    current_length = len(current_chunk[0]) + 1
        else:
            current_chunk.append(word)
            current_length += word_length
            
    if current_chunk:
        chunks.append(separator.join(current_chunk))
        
    return chunks

def extract_mentions(message: str) -> List[str]:
    """Extract IRC nicknames mentioned in a message.
    
    Args:
        message: Message text
        
    Returns:
        List[str]: List of mentioned nicknames
    """
    # Match IRC nicknames (alphanumeric, -, _, and |)
    pattern = r'@?(\w[-\w|]*)'
    mentions = re.findall(pattern, message)
    return [nick for nick in mentions if nick]

def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent IRC injection.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        str: Sanitized text
    """
    # Remove IRC control characters
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    
    # Remove potential IRC command characters
    text = text.replace('/', '').replace('\\', '')
    
    # Limit length
    max_length = 400
    if len(text) > max_length:
        text = text[:max_length] + '...'
        
    return text.strip()