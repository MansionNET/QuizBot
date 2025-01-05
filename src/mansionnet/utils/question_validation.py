"""Utilities for question validation and answer matching."""
import re
from typing import List, Set

# Words that suggest uncertain or ongoing events
UNCERTAIN_TERMS = {
    'recently', 'just', 'latest', 'current', 'ongoing', 'now',
    'this year', 'this month', 'this week', 'today'
}

# Words that suggest absolute claims that need verification
ABSOLUTE_CLAIMS = {
    'first', 'only', 'best', 'most', 'youngest', 'oldest',
    'highest', 'lowest', 'biggest', 'smallest'
}

# Common answer variations to support
ANSWER_VARIATIONS = {
    'epic games': ['epic'],
    'meta': ['facebook'],
    'microsoft': ['ms'],
    'playstation': ['ps', 'ps4', 'ps5'],
    'netflix': ['nflx'],
    'call of duty': ['cod'],
    'fortnite': ['fn'],
    'instagram': ['ig', 'insta'],
}

def has_uncertain_timing(question: str) -> bool:
    """Check if question refers to uncertain or recent timing."""
    return any(term in question.lower() for term in UNCERTAIN_TERMS)

def has_absolute_claim(question: str) -> bool:
    """Check if question makes an absolute claim that needs verification."""
    return any(claim in question.lower() for claim in ABSOLUTE_CLAIMS)

def normalize_answer(answer: str) -> str:
    """Normalize an answer for comparison."""
    # Remove articles and extra whitespace
    answer = re.sub(r'\b(the|a|an)\b', '', answer.lower())
    answer = ' '.join(answer.split())
    return answer

def get_acceptable_answers(answer: str) -> Set[str]:
    """Get all acceptable variations of an answer."""
    answer = normalize_answer(answer)
    variations = {answer}
    
    # Add known variations
    for main_answer, alternates in ANSWER_VARIATIONS.items():
        if answer == normalize_answer(main_answer):
            variations.update(alternates)
            break
        for alt in alternates:
            if answer == normalize_answer(alt):
                variations.add(main_answer)
                variations.update(alternates)
                break
    
    # Add singular/plural variations
    if not answer.endswith('s'):
        variations.add(answer + 's')
    else:
        variations.add(answer[:-1])
    
    return variations

def is_answer_match(user_answer: str, correct_answer: str) -> bool:
    """Check if a user's answer matches any acceptable variation."""
    user_answer = normalize_answer(user_answer)
    acceptable_answers = get_acceptable_answers(correct_answer)
    
    # Direct match with any acceptable answer
    if user_answer in acceptable_answers:
        return True
    
    # Check if answer is a subset/superset of correct answer (for compound answers)
    user_words = set(user_answer.split())
    for acceptable in acceptable_answers:
        acceptable_words = set(acceptable.split())
        if user_words.issubset(acceptable_words) or acceptable_words.issubset(user_words):
            return True
    
    # For single-word answers, check for close matches
    if len(user_words) == 1 and len(acceptable_words) == 1:
        user_word = user_words.pop()
        acceptable_word = acceptable_words.pop()
        # Check if user answer is a substring of acceptable answer
        if len(user_word) > 3 and (user_word in acceptable_word or acceptable_word in user_word):
            return True
    
    return False

def validate_question_content(question: str, answer: str) -> tuple[bool, str]:
    """Validate question content and format.
    Returns (is_valid, reason_if_invalid)"""
    
    # Check question length
    if len(question.split()) > 15:
        return False, "Question is too long"
    
    # Check answer length
    if len(answer.split()) > 3:
        return False, "Answer is too long"
    
    # Check for uncertain timing
    if has_uncertain_timing(question):
        return False, "Question refers to uncertain timing"
    
    # Check for unverifiable absolute claims
    if has_absolute_claim(question):
        return False, "Question makes unverifiable absolute claim"
    
    # Check for numeric specificity
    if re.search(r'\b\d{4}\b', question):
        return False, "Question contains specific year"
    
    # Check for overly complex language
    avg_word_length = sum(len(word) for word in question.split()) / len(question.split())
    if avg_word_length > 8:
        return False, "Question uses overly complex language"
    
    return True, ""

def clean_question_text(question: str) -> str:
    """Clean and format question text."""
    # Remove extra whitespace
    question = ' '.join(question.split())
    
    # Ensure proper capitalization
    question = question[0].upper() + question[1:]
    
    # Ensure question ends with question mark
    if not question.endswith('?'):
        question += '?'
    
    return question