"""Text processing utilities for quiz game."""
from difflib import SequenceMatcher
from typing import Tuple, Dict, Set
import re
import unicodedata

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
            "gaudi": {"gaudí", "gaudy", "gaudi", "antoni gaudi", "antonio gaudi"},
            "shakespeare": {"william shakespeare", "shakespear"},
            "beethoven": {"ludwig van beethoven", "ludvig beethoven", "bethoven"},
            "doctor who": {"who", "the doctor", "dr who"},
            "michelangelo": {"michaelangelo", "michel angelo"},
            "austen": {"jane austen", "austin", "austeen", "jane austin"},
            
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
            "soviet union": {"ussr", "soviet", "russia"},
            
            # Historical Groups
            "ancient britons": {"britons", "ancient brits", "celtic britons"},
            "monks": {"monk", "monastics", "monastic"},
            "monastery": {"monasteries", "monastic", "abbey"}
        }
        
        # Build reverse lookup for variations
        self.reverse_variations = {}
        for main, variants in self.variations.items():
            for variant in variants:
                self.reverse_variations[variant] = main

    def remove_diacritics(self, text: str) -> str:
        """Remove diacritical marks from text."""
        return ''.join(c for c in unicodedata.normalize('NFKD', text)
                      if not unicodedata.combining(c))
                
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower().strip()
        text = self.remove_diacritics(text)  # Handle diacritics
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text
        
    def get_similarity_ratio(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a, b).ratio()

    def check_name_match(self, user_answer: str, correct_answer: str) -> bool:
        """Special handling for name matching."""
        # Check if either answer contains spaces (indicating a full name)
        if ' ' in user_answer or ' ' in correct_answer:
            user_parts = set(user_answer.split())
            correct_parts = set(correct_answer.split())
            
            # Check if all parts of the shorter name are in the longer name
            if len(user_parts) < len(correct_parts):
                return all(any(self.get_similarity_ratio(up, cp) > 0.8 for cp in correct_parts) 
                          for up in user_parts)
            else:
                return all(any(self.get_similarity_ratio(cp, up) > 0.8 for up in user_parts) 
                          for cp in correct_parts)
        
        return False
        
    def is_match(self, user_answer: str, correct_answer: str, threshold: float = 0.85) -> bool:
        """Check if user's answer matches the correct answer."""
        user_answer = self.normalize_text(user_answer)
        correct_answer = self.normalize_text(correct_answer)
        
        # Direct match after normalization
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
            
        # Try name matching for longer answers
        if len(user_answer) > 3 and len(correct_answer) > 3:
            if self.check_name_match(user_answer, correct_answer):
                return True
            
        # More lenient threshold for short answers
        current_threshold = threshold
        if len(correct_answer) <= 5:
            current_threshold = 0.9  # Stricter for short answers
        elif len(correct_answer) >= 10:
            current_threshold = 0.8  # More lenient for longer answers
            
        # Fuzzy matching for typos
        similarity = self.get_similarity_ratio(user_answer, correct_answer)
        if similarity >= current_threshold:
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