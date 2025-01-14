"""Enhanced validation utilities for quiz questions."""
import logging
import re
from typing import Dict, List, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"

@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    message: str

class QuestionValidator:
    """Enhanced question validator with improved checks and internationalization."""
    
    def __init__(self):
        self.valid_starters = {
            'what', 'which', 'who', 'where', 'when', 'how many',
            'how much', 'in what', 'on what', 'at what', 'why',
            'from what', 'for what', 'name the'
        }
        
        # Updated ambiguous words
        self.ambiguous_words = {
            'many', 'some', 'few', 'several', 'various', 'different',
            'any', 'other', 'such', 'like', 'similar', 'about'
        }
        
        # Multiple answer indicators to avoid
        self.multiple_answer_indicators = {
            'and', 'or', 'examples', 'list', 'name some', 'such as',
            'including', 'included', 'among others', 'etc'
        }
        
        # Updated subjective terms
        self.subjective_terms = {
            'best', 'worst', 'greatest', 'least', 'most', 'famous',
            'popular', 'important', 'interesting', 'beautiful', 'ugly',
            'good', 'bad', 'better', 'worse', 'amazing', 'awesome',
            'fantastic', 'wonderful', 'terrible', 'horrible'
        }
        
        # Updated relative time terms
        self.relative_time_terms = {
            'recent', 'current', 'modern', 'new', 'latest', 'today',
            'now', 'contemporary', 'present', 'recently', 'upcoming',
            'future', 'past', 'soon', 'lately'
        }
        
        # Expanded valid multi-word prefixes
        self.valid_prefixes = {
            'mount', 'lake', 'saint', 'new', 'north', 'south', 'east', 'west',
            'prince', 'princess', 'king', 'queen', 'sir', 'lady', 'lord',
            'cape', 'fort', 'port', 'san', 'santa', 'los', 'las', 'el', 'de',
            'van', 'von', 'sheikh', 'sultan', 'raja', 'grand'
        }
        
        # Updated valid units
        self.valid_units = {
            'meters', 'kilometers', 'centimeters', 'millimeters',
            'feet', 'miles', 'yards', 'inches',
            'kilograms', 'grams', 'pounds', 'ounces',
            'celsius', 'fahrenheit', 'kelvin',
            'years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds',
            'square kilometers', 'square miles', 'hectares', 'acres'
        }
        
        # Problematic patterns
        self.problematic_patterns = [
            (r'\b(and|or)\b', "Question contains conjunction suggesting multiple parts"),
            (r'\b(can|could|might|may)\b', "Question contains modal verb suggesting uncertainty"),
            (r'\b(usually|sometimes|often|occasionally)\b', "Question contains frequency term"),
            (r'\b(probably|possibly|maybe)\b', "Question contains uncertainty term"),
            (r'\b(etc|etc\.)\b', "Question contains 'etc' suggesting incomplete list"),
            (r'\b(around|approximately|about)\b', "Question contains approximation term"),
            (r'\(?(\?|\(|\))\)?$', "Question contains unnecessary punctuation"),
            (r'\b(famous|well-known|popular)\b', "Question contains subjective popularity term"),
            (r'\b(difficult|easy|hard|simple)\b', "Question contains subjective difficulty term"),
            (r'\b(thing|stuff|something)\b', "Question contains vague terminology")
        ]
        
        # Self-referential patterns
        self.self_referential_patterns = [
            (r'\b(what|which) (\w+) (?:is|are) .*\2\b', "Question is self-referential"),
            (r'\b(\w+) (?:used|found|contained) in .*\1\b', "Question reveals its own answer"),
            (r'\bmakes up .*\b(\w+).*\1\b', "Question reveals its own answer")
        ]
        
        # International sports coverage
        self.sports_categories = {
            'cricket': ['test', 't20', 'odi', 'ipl', 'bbl', 'county'],
            'football': ['premier league', 'la liga', 'bundesliga', 'serie a', 'champions league'],
            'rugby': ['union', 'league', 'six nations', 'world cup'],
            'basketball': ['nba', 'euroleague', 'fiba', 'cba'],
            'tennis': ['grand slam', 'atp', 'wta', 'davis cup'],
            'baseball': ['mlb', 'npb', 'kbo'],
            'hockey': ['nhl', 'khl', 'iihf'],
            'volleyball': ['fivb', 'nations league'],
            'table tennis': ['ittf', 'world championships'],
            'badminton': ['bwf', 'thomas cup', 'uber cup']
        }
        
        # Cultural diversity categories
        self.cultural_categories = {
            'world_literature': ['asian', 'african', 'european', 'american', 'oceanian'],
            'global_cuisine': ['asian', 'african', 'european', 'american', 'middle_eastern'],
            'world_music': ['classical', 'folk', 'contemporary', 'traditional'],
            'international_cinema': ['bollywood', 'hollywood', 'european', 'asian', 'african'],
            'world_history': ['ancient', 'medieval', 'modern', 'contemporary'],
            'traditional_arts': ['visual', 'performing', 'crafts', 'architecture']
        }
        
        # Category usage tracking
        self.category_usage = {}

    def validate_question(self, data: Dict, session_id: str = None) -> List[ValidationIssue]:
        """Validate a question with enhanced checks."""
        issues = []
        
        # Track category usage
        if session_id:
            if session_id not in self.category_usage:
                self.category_usage[session_id] = set()
            category = data.get('category', '').lower()
            if category in self.category_usage[session_id]:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Category '{category}' already used in this session"
                ))
            else:
                self.category_usage[session_id].add(category)

        # Basic structure validation
        question = data.get('question', '').strip()
        answer = data.get('answer', '').strip()
        fun_fact = data.get('fun_fact', '').strip()
        category = data.get('category', '').lower()

        if len(question) < 15:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question too short (min 15 chars)"
            ))

        if not answer:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Answer is required"
            ))

        if len(fun_fact) < 20:
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Fun fact too short (min 20 chars)"
            ))

        # Question format validation
        if not question.endswith('?'):
            question += '?'
        
        # Remove trailing artifacts
        question = re.sub(r'\s*\(\?\s*$', '?', question)
        
        # Check question starter
        if not any(question.lower().startswith(starter) for starter in self.valid_starters):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Question must start with valid question word"
            ))

        # Check for ambiguous language
        for word in self.ambiguous_words:
            if f" {word} " in f" {question.lower()} ":
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains ambiguous word: {word}"
                ))

        # Check for multiple answer indicators
        for indicator in self.multiple_answer_indicators:
            if indicator in question.lower():
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question suggests multiple answers: {indicator}"
                ))

        # Check for subjective terms
        for term in self.subjective_terms:
            if term in question.lower():
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Question contains subjective term: {term}"
                ))

        # Check for relative time terms
        for term in self.relative_time_terms:
            if term in question.lower():
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"Question contains relative time term: {term}"
                ))

        # Check for self-referential patterns
        for pattern, message in self.self_referential_patterns:
            if re.search(pattern, question.lower()):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    message
                ))

        # Fun fact validation
        if question.lower() in fun_fact.lower() or answer.lower() in fun_fact.lower():
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "Fun fact should not repeat question or answer verbatim"
            ))

        # Check for cut-off sentences in fun fact
        if not fun_fact.rstrip().endswith(('.', '!', '?')):
            issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "Fun fact appears to be cut off"
            ))

        # Category-specific validation
        self._validate_category_specific(data, issues)

        return issues

    def _validate_category_specific(self, data: Dict, issues: List[ValidationIssue]):
        """Perform category-specific validation."""
        category = data.get('category', '').lower()
        question = data.get('question', '').lower()
        answer = data.get('answer', '').lower()
        fun_fact = data.get('fun_fact', '').lower()

        if category == 'science':
            # Validate scientific answers
            if re.search(r'\b(thing|stuff|something)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Science questions should use precise terminology"
                ))
            
            # Enforce metric units
            if re.search(r'\b\d+\s*(?:foot|feet|inch|inches|mile|miles|pound|pounds|fahrenheit)\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Use metric units for science questions"
                ))

        elif category == 'history':
            # Standardize date formats
            if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', question) or \
               re.search(r'\b\d{1,2}-\d{1,2}-\d{2,4}\b', question):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Use year only for historical dates unless month is crucial"
                ))

            # Remove era designations from answers
            if re.search(r'\b(CE|BCE|AD|BC)\b', answer):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Remove era designations (CE/BCE/AD/BC) from year answers"
                ))

        elif category == 'geography':
            # Validate place names
            if '_' in answer:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Don't use underscores in geographic names"
                ))

            # Check for proper capitalization
            if any(word.islower() and len(word) > 3 for word in answer.split()):
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "Geographic names should be properly capitalized"
                ))

        elif category == 'sports':
            # Validate international sports coverage
            sport_mentioned = False
            for sport, leagues in self.sports_categories.items():
                if sport in question or any(league in question for league in leagues):
                    sport_mentioned = True
                    break
            
            if not sport_mentioned:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Consider specifying the sport or competition"
                ))

            # Validate score/record formats
            if re.search(r'\b\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\b', answer):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Consider using ranges for sports records/scores"
                ))

        elif category == 'entertainment':
            # Check for regional bias
            western_terms = ['hollywood', 'oscar', 'emmy', 'grammy']
            if any(term in question.lower() for term in western_terms):
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "Consider including non-Western entertainment"
                ))

        elif category in self.cultural_categories:
            # Validate cultural representation
            region_mentioned = False
            for region in self.cultural_categories[category]:
                if region in question.lower():
                    region_mentioned = True
                    break
            
            if not region_mentioned:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"Consider specifying cultural region for {category}"
                ))

    def reset_category_usage(self, session_id: str):
        """Reset category usage tracking for a session."""
        if session_id in self.category_usage:
            self.category_usage[session_id] = set()
