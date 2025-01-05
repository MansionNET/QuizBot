"""Text processing utilities for the QuizBot."""
from typing import Tuple
import re

def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Convert to lowercase
    text = text.lower()
    # Remove special characters
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text

def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings."""
    str1 = normalize_text(str1)
    str2 = normalize_text(str2)
    
    # Direct match
    if str1 == str2:
        return 1.0
    
    # Length similarity
    len_ratio = min(len(str1), len(str2)) / max(len(str1), len(str2))
    
    # Character similarity using Levenshtein distance
    distance = levenshtein_distance(str1, str2)
    max_length = max(len(str1), len(str2))
    similarity = 1 - (distance / max_length)
    
    # Combined similarity score
    return (len_ratio + similarity) / 2

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def is_answer_match(user_answer: str, correct_answer: str, threshold: float = 0.85) -> bool:
    """Determine if a user's answer matches the correct answer."""
    # Normalize both answers
    user_answer = normalize_text(user_answer)
    correct_answer = normalize_text(correct_answer)
    
    # Check for exact match
    if user_answer == correct_answer:
        return True
    
    # Check for plural/singular variations
    if user_answer + 's' == correct_answer or user_answer == correct_answer + 's':
        return True
    
    # Check for substring match (if answer is long enough)
    if len(user_answer) > 3 and (user_answer in correct_answer or correct_answer in user_answer):
        return True
    
    # Calculate similarity for longer answers
    if len(user_answer) > 3 and len(correct_answer) > 3:
        similarity = calculate_similarity(user_answer, correct_answer)
        return similarity >= threshold
    
    return False

def format_time(seconds: int) -> str:
    """Format time duration in a human-readable way."""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if remaining_seconds == 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{minutes}m {remaining_seconds}s"

def truncate_text(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncate text to a maximum length while preserving words."""
    if len(text) <= max_length:
        return text
        
    truncated = text[:max_length-len(suffix)].rsplit(' ', 1)[0]
    return truncated + suffix

def extract_command(message: str) -> Tuple[str, str]:
    """Extract command and arguments from a message."""
    parts = message.strip().split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ''
    return command, args
