"""Text processing utilities for quiz game."""
from difflib import SequenceMatcher
from typing import Tuple, Dict, Set
import re

class AnswerMatcher:
    """Improved answer matching system with support for variations and alternatives."""
    
    def __init__(self):
        self.variations = {
            # Companies and Platforms
            "google": {"alphabet", "google inc", "google inc.", "google corporation"},
            "meta": {"facebook", "meta platforms", "fb", "facebook inc", "meta inc"},
            "microsoft": {"ms", "microsoft corporation", "microsoft corp"},
            "apple": {"apple inc", "apple computer", "apple computers"},
            "epic games": {"epic", "epic store", "epic launcher"},
            "disney+": {"disney", "disney plus", "disneyplus"},
            "netflix": {"netflix inc", "netflix streaming"},
            
            # Gaming
            "playstation": {"ps", "ps1", "ps2", "ps3", "ps4", "ps5", "sony playstation"},
            "xbox": {"microsoft xbox", "xbox console"},
            "nintendo": {"nintendo co", "nintendo corporation"},
            "minecraft": {"mine craft"},
            
            # Historical/Famous People
            "thomas edison": {"edison", "thomas a edison", "t edison"},
            "leonardo da vinci": {"da vinci", "davinci", "leonardo", "leonardo davinci"},
            
            # Sports and Events
            "olympics": {"olympic games", "olympic", "the olympics"},
            "world cup": {"fifa world cup", "soccer world cup", "football world cup"},
            
            # Technology
            "artificial intelligence": {"ai"},
            "virtual reality": {"vr"},
            "operating system": {"os"},
            
            # Elements and Materials
            "silicon": {"si", "silicon semiconductor"},
            "nitrogen": {"n2", "n"},
            "oxygen": {"o2", "o"},
            
            # Countries and Organizations
            "united states": {"usa", "us", "united states of america", "america"},
            "united kingdom": {"uk", "britain", "great britain"},
            "european union": {"eu"},
            "soviet union": {"ussr", "soviet", "russia"}
        }
        
        # Build reverse lookup for variations
        self.reverse_variations = {}
        for main, variants in self.variations.items():
            for variant in variants:
                self.reverse_variations[variant] = main
                
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text
        
    def get_similarity_ratio(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a, b).ratio()
        
    def is_match(self, user_answer: str, correct_answer: str, threshold: float = 0.85) -> bool:
        """Check if user's answer matches the correct answer."""
        user_answer = self.normalize_text(user_answer)
        correct_answer = self.normalize_text(correct_answer)
        
        # Direct match
        if user_answer == correct_answer:
            return True
            
        # Check common variations
        user_main = self.reverse_variations.get(user_answer)
        correct_main = self.reverse_variations.get(correct_answer)
        
        if user_main and correct_main and user_main == correct_main:
            return True
            
        if user_main:
            user_answer = user_main
        if correct_main:
            correct_answer = correct_main
            
        # Check variations
        if correct_answer in self.variations:
            if user_answer in self.variations[correct_answer]:
                return True
                
        # Handle plural/singular
        if user_answer.endswith('s') and user_answer[:-1] == correct_answer:
            return True
        if correct_answer.endswith('s') and correct_answer[:-1] == user_answer:
            return True
            
        # Fuzzy matching for typos
        similarity = self.get_similarity_ratio(user_answer, correct_answer)
        if similarity >= threshold:
            return True
            
        return False

# Global matcher instance
_matcher = AnswerMatcher()

def is_answer_match(user_answer: str, correct_answer: str) -> bool:
    """Global function to check answer matches."""
    return _matcher.is_match(user_answer, correct_answer)

def extract_command(message: str) -> Tuple[str, str]:
    """Extract command and arguments from a message."""
    parts = message.strip().split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return command, args