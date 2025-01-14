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
        # Valid question starters
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
            'future', 'past'
        }
        
        # Valid multi-word prefixes for answers
        self.valid_prefixes = {
            'mount', 'lake', 'saint', 'new', 'north', 'south', 'east', 'west',
            'prince', 'princess', 'king', 'queen', 'sir', 'lady', 'lord',
            'cape', 'fort', 'port', 'san', 'santa', 'los', 'las', 'el', 'de'
        }
        
        # Valid units for numerical answers
        self.valid_units = {
            'feet', 'meters', 'kilometers', 'miles', 'kg', 'pounds',
            'celsius', 'fahrenheit', 'years', 'hours', 'minutes',
            'seconds', 'degrees', 'square miles', 'square kilometers'
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

        # Remove trailing (? and other artifacts
        question = re.sub(r'\s*\(\?\s*$', '', question)
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

        # Answer validation
        answer_words = answer.split()
        is_numerical = bool(re.match(r'^\d+(\.\d+)?\s*[a-zA-Z]*$', answer))
        has_valid_prefix = any(prefix in answer.lower() for prefix in self.valid_prefixes)
        has_valid_unit = any(unit in answer.lower() for unit in self.valid_units)
        
        # Allow longer answers for specific cases
        if len(answer_words) > 3 and not (is_numerical or has_valid_prefix or has_valid_unit):
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
        if question.lower() in fun_fact.lower() or answer.lower() in fun_fact.lower():
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should not repeat question or answer verbatim"
            ))
            
        if len(fun_fact.split()) < 8:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should be more detailed"
            ))

        # Don't allow fun facts that just say "Related to..."
        if fun_fact.lower().startswith("related to"):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Fun fact must provide actual information"
            ))

        # Check for problematic patterns
        for pattern, message in self.problematic_patterns:
            if re.search(pattern, question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    message
                ))

        # Category-specific validation
        self._validate_category_specific(data, issues)

        return issues

    def _validate_category_specific(self, data: Dict, issues: List[ValidationIssue]):
        """Perform category-specific validation."""
        category = data.get("category", "").lower()
        question = data.get("question", "").lower()
        answer = data.get("answer", "").lower()
        fun_fact = data.get("fun_fact", "").lower()

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
            date_patterns = [
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # DD/MM/YYYY
                r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',  # DD-MM-YYYY
            ]
            for pattern in date_patterns:
                if re.search(pattern, question) or re.search(pattern, answer):
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR,
                        "Use year only for historical dates unless month is crucial"
                    ))

            # Remove CE/BCE from answers
            if "ce" in answer or "bce" in answer:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Remove CE/BCE from year answers"
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

        elif category == "arts":
            # Check for proper artist/work attribution
            if "painted" in question or "composed" in question:
                if len(answer.split()) == 1:
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING,
                        "Consider using full name for artists"
                    ))

    def create_answer_variants(self, answer: str) -> List[str]:
        """Create variations of the answer for matching."""
        variants = {answer.lower()}
        
        # Remove special characters and extra spaces
        clean_answer = re.sub(r'[^\w\s]', '', answer.lower())
        variants.add(clean_answer)
        
        # Handle numbers
        if answer.replace(',', '').replace('.', '').isdigit():
            num = int(float(answer.replace(',', '')))
            variants.add(str(num))
            variants.add(f"{num:,}")  # With commas
            
        # Common prefixes to try removing
        prefixes = ['mount ', 'mt. ', 'mt ', 'saint ', 'st. ', 'lake ']
        for prefix in prefixes:
            if answer.lower().startswith(prefix):
                variants.add(answer[len(prefix):])
                
        # Handle special cases
        if ' and ' in answer:
            variants.add(answer.replace(' and ', ' & '))
            
        if re.match(r'^\d+(?:st|nd|rd|th)', answer):
            # Convert ordinal numbers (1st -> 1, 2nd -> 2)
            base = re.match(r'^\d+', answer).group()
            variants.add(base)
            
        return list(variants)