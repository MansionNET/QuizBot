"""Validation utilities for quiz questions."""
import logging
import re
from typing import Dict, List, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"

@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    message: str

class QuestionValidator:
    def __init__(self):
        # Valid question starters - expanded list
        self.valid_starters = {
            'what', 'which', 'who', 'where', 'when', 'how many',
            'how much', 'in what', 'on what', 'at what', 'why',
            'from what', 'for what'
        }
        
        # Words that suggest ambiguity
        self.ambiguous_words = {
            'many', 'some', 'few', 'several', 'various', 'different',
            'any', 'other', 'such', 'like', 'similar'
        }
        
        # Words that suggest multiple answers
        self.multiple_answer_indicators = {
            'example', 'examples', 'among', 'including', 'included',
            'list', 'give', 'name some', 'tell me some'
        }
        
        # Subjective terms
        self.subjective_terms = {
            'best', 'worst', 'greatest', 'least', 'famous',
            'popular', 'important', 'interesting', 'beautiful', 'ugly',
            'good', 'bad', 'better', 'worse', 'amazing', 'awesome'
        }
        
        # Time-relative terms
        self.relative_time_terms = {
            'recent', 'current', 'modern', 'new', 'latest', 'today',
            'now', 'contemporary', 'present', 'recently', 'upcoming',
            'future', 'past', 'ancient'
        }
        
        # Valid multi-word prefixes for answers
        self.valid_prefixes = {
            'mount', 'lake', 'saint', 'new', 'north', 'south', 'east', 'west',
            'prince', 'princess', 'king', 'queen', 'sir', 'lady', 'lord'
        }
        
        # Valid units for numerical answers
        self.valid_units = {
            'feet', 'meters', 'kilometers', 'miles', 'kg', 'pounds',
            'celsius', 'fahrenheit', 'years', 'hours', 'minutes',
            'seconds', 'degrees'
        }

    def validate_question(self, data: Dict) -> List[ValidationIssue]:
        """Validate a question and return list of issues found."""
        issues = []
        
        # Basic structure checks
        if len(data.get("question", "")) < 15:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question is too short (min 15 chars)"
            ))
        
        if len(data.get("answer", "")) < 1:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Answer is too short (min 1 char)"
            ))
            
        if len(data.get("fun_fact", "")) < 20:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Fun fact is too short (min 20 chars)"
            ))

        question = data.get("question", "").lower().strip()
        answer = data.get("answer", "").lower().strip()
        fun_fact = data.get("fun_fact", "").lower().strip()

        # Question format checks
        if not question.endswith("?"):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question must end with a question mark"
            ))

        # Check question starter
        if not any(question.startswith(starter) for starter in self.valid_starters):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question must start with valid question word"
            ))

        # Length checks
        words = question.split()
        if len(words) > 15:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                f"Question is too long ({len(words)} words, max 15)"
            ))

        # Answer validation with special cases
        answer_words = answer.split()
        if len(answer_words) > 3:
            # Check if it's a valid numerical answer with units
            is_numerical = bool(re.match(r'^\d+(\.\d+)?\s+[a-z]+$', answer))
            is_valid_unit = any(unit in answer for unit in self.valid_units)
            has_valid_prefix = any(prefix in answer.lower() for prefix in self.valid_prefixes)
            
            if not (is_numerical and is_valid_unit) and not has_valid_prefix:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Answer too long ({len(answer_words)} words, max 3)"
                ))

        # Check for multiple answer indicators
        for word in self.multiple_answer_indicators:
            if word in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question contains word suggesting multiple answers: {word}"
                ))

        # Check for relative time terms
        for term in self.relative_time_terms:
            if term in question:
                # Allow 'ancient' in history category
                if term == 'ancient' and data.get('category') == 'history':
                    continue
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question contains relative time term: {term}"
                ))

        # Check for subjective terms
        for term in self.subjective_terms:
            if term in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains subjective term: {term}"
                ))

        # Fun fact validation
        if question in fun_fact or answer in fun_fact:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should not repeat question or answer verbatim"
            ))
            
        if len(fun_fact.split()) < 8:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should be more detailed"
            ))

        # Category-specific validation
        self._validate_category_specific(data, issues)

        return issues

    def _validate_category_specific(self, data: Dict, issues: List[ValidationIssue]):
        """Perform category-specific validation."""
        category = data.get("category", "").lower()
        question = data.get("question", "").lower()
        answer = data.get("answer", "").lower()

        if category == "science":
            # Validate scientific answers
            if re.search(r'\b(thing|stuff|something)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Science questions should use precise terminology"
                ))
                
            # Check for unit consistency
            if re.search(r'\b\d+\s*(?:f|ft|foot|feet)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Use metric units for science questions"
                ))

        elif category == "history":
            # Validate date formats
            if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Use year only for historical dates unless month is crucial"
                ))

        elif category == "geography":
            # Validate place names
            if any(word.islower() and len(word) > 3 for word in answer.split()):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Geographic names should be properly capitalized"
                ))

        elif category == "entertainment":
            # Validate movie/show titles
            if '"' in question and '"' not in answer and len(answer.split()) == 1:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Consider including full title for movies/shows"
                ))

        elif category == "sports":
            # Validate sports terminology
            if re.search(r'\b(match|game|competition)\b', question) and not re.search(r'\b(in|at|during)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Specify the context for sports events"
                ))