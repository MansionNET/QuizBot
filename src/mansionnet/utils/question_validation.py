"""Utilities for validating quiz questions."""
import re
from typing import Tuple, Dict, Set
from ..config.settings import AMBIGUOUS_TERMS, COMPLEX_TERMS, ALTERNATIVE_ANSWERS

def clean_question_text(text: str) -> str:
    """Clean and normalize question text."""
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Ensure question ends with question mark
    if not text.endswith('?'):
        text += '?'
    
    # Capitalize first letter
    text = text[0].upper() + text[1:]
    
    return text

def normalize_answer(answer: str) -> str:
    """Normalize answer text for consistent comparison."""
    # Convert to lowercase and remove extra spaces
    answer = re.sub(r'\s+', ' ', answer.strip().lower())
    
    # Remove articles and common prefixes
    answer = re.sub(r'^(the|a|an) ', '', answer)
    
    # Remove punctuation except hyphens
    answer = re.sub(r'[^\w\s-]', '', answer)
    
    return answer

def is_valid_length(text: str, min_words: int = 3, max_words: int = 15) -> bool:
    """Check if text length is within acceptable range."""
    words = text.split()
    return min_words <= len(words) <= max_words

def contains_prohibited_terms(text: str, terms: Set[str]) -> bool:
    """Check if text contains any prohibited terms."""
    text_lower = text.lower()
    return any(term.lower() in text_lower for term in terms)

def is_specific_enough(question: str) -> bool:
    """Check if question is specific enough to have a clear answer."""
    vague_patterns = [
        r'what (kind|type|sort) of',
        r'how (many|much)',
        r'(who|what|which) are',
        r'(can|could) you',
        r'tell me'
    ]
    return not any(re.search(pattern, question.lower()) for pattern in vague_patterns)

def has_clear_context(question: str) -> bool:
    """Check if question provides enough context."""
    # Questions should generally mention a specific subject/topic
    return any(x in question.lower() for x in ['who', 'what', 'which', 'where', 'when', 'how'])

def validate_question_content(
    question: str,
    answer: str,
    min_question_length: int = 3,
    max_question_length: int = 15,
    max_answer_words: int = 3
) -> Tuple[bool, str]:
    """Validate question and answer content."""
    # Check question length
    if not is_valid_length(question, min_question_length, max_question_length):
        return False, "Question length outside acceptable range"
    
    # Check answer length
    if len(answer.split()) > max_answer_words:
        return False, "Answer too long"
    
    # Check for ambiguous terms
    if contains_prohibited_terms(question, AMBIGUOUS_TERMS):
        return False, "Question contains ambiguous terms"
    
    # Check for complex terms
    if contains_prohibited_terms(question, COMPLEX_TERMS):
        return False, "Question contains complex terms"
    
    # Check for specific enough question
    if not is_specific_enough(question):
        return False, "Question not specific enough"
    
    # Check for clear context
    if not has_clear_context(question):
        return False, "Question lacks clear context"
    
    # Check answer format
    if not re.match(r'^[\w\s-]+$', answer):
        return False, "Answer contains invalid characters"
    
    return True, "Valid question"

def get_alternative_answers(answer: str) -> Set[str]:
    """Get all acceptable alternative answers for a given answer."""
    alternatives = {answer}
    
    # Check main alternatives
    if answer in ALTERNATIVE_ANSWERS:
        alternatives.update(ALTERNATIVE_ANSWERS[answer])
    
    # Check reverse mapping
    for main_answer, alts in ALTERNATIVE_ANSWERS.items():
        if answer in alts:
            alternatives.add(main_answer)
            alternatives.update(alts)
    
    return alternatives

def is_answer_match(user_answer: str, correct_answer: str) -> bool:
    """Check if user's answer matches any acceptable version of the correct answer."""
    user_answer = normalize_answer(user_answer)
    correct_answer = normalize_answer(correct_answer)
    
    # Get all acceptable versions of the correct answer
    valid_answers = get_alternative_answers(correct_answer)
    
    # Check against all valid answers
    return user_answer in {normalize_answer(ans) for ans in valid_answers}