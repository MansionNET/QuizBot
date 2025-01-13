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
        # Words that suggest ambiguity
        self.ambiguous_words = {
            'many', 'some', 'few', 'several', 'various', 'different',
            'most', 'any', 'other', 'such', 'like', 'similar'
        }
        
        # Words that suggest multiple answers
        self.multiple_answer_indicators = {
            'example', 'examples', 'among', 'including', 'included',
            'one', 'few', 'name', 'list', 'give'
        }
        
        # Subjective terms
        self.subjective_terms = {
            'best', 'worst', 'greatest', 'most', 'least', 'famous',
            'popular', 'important', 'interesting', 'beautiful', 'ugly',
            'good', 'bad', 'better', 'worse', 'amazing', 'awesome'
        }
        
        # Time-relative terms
        self.relative_time_terms = {
            'recent', 'current', 'modern', 'new', 'latest', 'today',
            'now', 'contemporary', 'present', 'recently'
        }
        
        # Question starters that suggest multiple answers
        self.problematic_starters = {
            'list', 'name', 'give', 'tell me about', 'describe',
            'explain', 'discuss'
        }
        
        # Valid question starters
        self.valid_starters = {
            'what', 'which', 'who', 'where', 'when', 'how many',
            'how much', 'in what', 'on what', 'at what'
        }
        
        # Common question patterns that should be avoided
        self.problematic_patterns = [
            (r'\b(and|or)\b', "Question contains conjunction suggesting multiple parts or choices"),
            (r'\b(can|could|might|may)\b', "Question contains modal verb suggesting uncertainty"),
            (r'\b(usually|sometimes|often|occasionally)\b', "Question contains frequency term suggesting ambiguity"),
            (r'\b(probably|possibly|maybe)\b', "Question contains uncertainty term"),
            (r'\b(etc|etc\.)\b', "Question contains 'etc' suggesting incomplete list"),
            (r'\b(famous|well-known|popular)\b', "Question contains subjective popularity term"),
            (r'\b(difficult|easy|hard|simple)\b', "Question contains subjective difficulty term"),
            (r'\b(beautiful|pretty|ugly|nice)\b', "Question contains subjective aesthetic term")
        ]

    def validate_question(self, data: Dict) -> List[ValidationIssue]:
        """Validate a question and return list of issues found."""
        issues = []
        
        # Basic structure checks
        if len(data.get("question", "")) < 15:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question is too short (min 15 chars)"
            ))
        
        if len(data.get("answer", "")) < 2:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Answer is too short (min 2 chars)"
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
                "Question must start with valid question word (what, which, who, where, when, how many, in what)"
            ))

        # Check for problematic starters
        if any(question.startswith(starter) for starter in self.problematic_starters):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question starts with word that suggests multiple or open-ended answers"
            ))

        # Length checks
        words = question.split()
        if len(words) > 15:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                f"Question is too long ({len(words)} words, max 15)"
            ))

        answer_words = answer.split()
        if len(answer_words) > 3:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                f"Answer too long ({len(answer_words)} words, max 3)"
            ))

        # Check for answer in question
        if answer in question:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question contains exact answer"
            ))

        # Check for answer words in question
        for word in answer_words:
            if len(word) > 3 and word in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains answer word: {word}"
                ))

        # Check for ambiguous words
        for word in self.ambiguous_words:
            if word in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains ambiguous word: {word}"
                ))

        # Check for multiple answer indicators
        for word in self.multiple_answer_indicators:
            if word in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question contains word suggesting multiple answers: {word}"
                ))

        # Check for subjective terms
        for term in self.subjective_terms:
            if term in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains subjective term: {term}"
                ))

        # Check for relative time terms
        for term in self.relative_time_terms:
            if term in question:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question contains relative time term: {term}"
                ))

        # Check problematic patterns
        for pattern, message in self.problematic_patterns:
            if re.search(pattern, question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    message
                ))

        # Fun fact checks
        if question in fun_fact or answer in fun_fact:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should not repeat question or answer verbatim"
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
            # Check for proper scientific terminology
            if re.search(r'\b(thing|stuff|something)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Science questions should use precise terminology"
                ))

        elif category == "history":
            # Check for date format consistency
            date_patterns = [
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # DD/MM/YYYY
                r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',  # DD-MM-YYYY
            ]
            for pattern in date_patterns:
                if re.search(pattern, question) or re.search(pattern, answer):
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING,
                        "Use full year format for dates (YYYY)"
                    ))

        elif category == "geography":
            # Check for proper place name capitalization in answer
            if answer != answer.title() and len(answer.split()) == 1:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Geographic names should be capitalized"
                ))