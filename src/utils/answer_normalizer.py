"""Answer normalization utilities for quiz questions."""
from typing import Dict, Optional, Set
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AnswerNormalizer:
    """Enhanced answer normalizer with improved flexibility and internationalization."""
    
    def __init__(self):
        # Base configuration
        self.month_names = {
            'january': '01', 'february': '02', 'march': '03',
            'april': '04', 'may': '05', 'june': '06',
            'july': '07', 'august': '08', 'september': '09',
            'october': '10', 'november': '11', 'december': '12'
        }
        
        # Expanded unit conversions
        self.unit_conversions = {
            'inch': 'centimeter',
            'inches': 'centimeters',
            'foot': 'meter',
            'feet': 'meters',
            'mile': 'kilometer',
            'miles': 'kilometers',
            'pound': 'kilogram',
            'pounds': 'kilograms',
            'fahrenheit': 'celsius',
            'yard': 'meter',
            'yards': 'meters',
            'ounce': 'gram',
            'ounces': 'grams'
        }
        
        # Sport-specific score/record ranges (±5% tolerance)
        self.sport_ranges = {
            'basketball': 0.05,  # 5% tolerance for points
            'football': 0.05,    # 5% for goals/points
            'baseball': 0.05,    # 5% for runs/hits
            'cricket': 0.05,     # 5% for runs
            'rugby': 0.05        # 5% for points
        }
        
        # International sport variations
        self.sport_variations = {
            'soccer': ['football', 'association football'],
            'football': ['american football', 'gridiron'],
            'table tennis': ['ping pong', 'ping-pong'],
            'badminton': ['shuttlecock sport'],
        }
        
        # Geographic term variations
        self.geo_variations = {
            'united states': ['usa', 'us', 'america', 'united states of america'],
            'united kingdom': ['uk', 'britain', 'great britain'],
            'russia': ['russian federation'],
            'china': ["people's republic of china", 'prc'],
        }
        
        # Cultural variations
        self.cultural_variations = {
            # Foods
            'dumpling': ['jiaozi', 'gyoza', 'mandu', 'momo'],
            'flatbread': ['naan', 'pita', 'roti', 'tortilla'],
            # Instruments
            'drum': ['tabla', 'djembe', 'taiko'],
            'lute': ['oud', 'pipa', 'biwa'],
            # Art forms
            'theater': ['theatre', 'drama', 'stage performance'],
            'martial arts': ['kung fu', 'karate', 'judo', 'taekwondo']
        }

    def normalize_answer(self, answer: str, category: str, metadata: Dict = None) -> str:
        """Normalize an answer with enhanced flexibility and context awareness."""
        answer = answer.lower().strip()
        metadata = metadata or {}
        
        # Basic cleanup
        answer = re.sub(r'\s+', ' ', answer)  # Normalize whitespace
        answer = answer.replace('_', ' ')      # Replace underscores
        
        # Category-specific normalization
        if category == 'science':
            return self._normalize_science_answer(answer)
        elif category == 'history':
            return self._normalize_history_answer(answer)
        elif category == 'geography':
            return self._normalize_geography_answer(answer)
        elif category == 'sports':
            return self._normalize_sports_answer(answer, metadata)
        elif category == 'arts':
            return self._normalize_arts_answer(answer)
        elif category == 'entertainment':
            return self._normalize_entertainment_answer(answer)
        elif category == 'food_drink':
            return self._normalize_food_answer(answer)
        
        return answer

    def _normalize_sports_answer(self, answer: str, metadata: Dict) -> str:
        """Enhanced sports answer normalization with score/record flexibility."""
        sport_type = metadata.get('sport_type', '').lower()
        
        # Handle numerical answers (scores/records)
        if answer.replace('.', '').replace(',', '').isdigit():
            number = float(answer.replace(',', ''))
            # Apply sport-specific tolerance
            tolerance = self.sport_ranges.get(sport_type, 0.05)
            range_low = number * (1 - tolerance)
            range_high = number * (1 + tolerance)
            return f"{range_low:.1f}-{range_high:.1f}"
            
        # Handle sport name variations
        for main_name, variations in self.sport_variations.items():
            if answer in variations:
                return main_name
                
        return answer

    def _normalize_geography_answer(self, answer: str) -> str:
        """Enhanced geography answer normalization."""
        # Check for country/region variations
        for main_name, variations in self.geo_variations.items():
            if answer in variations:
                return main_name
                
        # Handle desert names correctly
        if 'desert' in answer:
            parts = answer.split()
            return ' '.join(part.capitalize() for part in parts)
            
        # Handle compass directions
        directions = ['north', 'south', 'east', 'west']
        words = answer.split()
        if words[0] in directions:
            return ' '.join(word.capitalize() for word in words)
            
        return answer

    def _normalize_history_answer(self, answer: str) -> str:
        """Enhanced history answer normalization."""
        # Remove CE/BCE/AD/BC and standardize years
        answer = re.sub(r'\s*(CE|BCE|AD|BC)$', '', answer)
        
        # Handle date ranges
        if '-' in answer and all(part.strip().isdigit() for part in answer.split('-')):
            start, end = answer.split('-')
            return f"{start.strip()}-{end.strip()}"
            
        # Handle centuries
        century_match = re.match(r'(\d+)(st|nd|rd|th)\s+century', answer)
        if century_match:
            num = int(century_match.group(1))
            return f"{num}th century"
            
        return answer

    def _normalize_science_answer(self, answer: str) -> str:
        """Normalize scientific answers."""
        # Convert units to metric
        for imperial, metric in self.unit_conversions.items():
            if imperial in answer:
                return answer.replace(imperial, metric)
        return answer

    def _normalize_arts_answer(self, answer: str) -> str:
        """Normalize arts and culture answers."""
        # Handle cultural variations
        for main_term, variations in self.cultural_variations.items():
            if answer in variations:
                return main_term
        return answer

    def _normalize_entertainment_answer(self, answer: str) -> str:
        """Normalize entertainment answers."""
        # Remove "The" from beginning of titles
        if answer.startswith('the '):
            return answer[4:]
        return answer

    def _normalize_food_answer(self, answer: str) -> str:
        """Normalize food and drink answers."""
        # Handle cultural food variations
        for main_term, variations in self.cultural_variations.items():
            if answer in variations and 'food' in self.cultural_variations:
                return main_term
        return answer

def create_answer_variants(answer: str) -> Set[str]:
    """Create a set of acceptable answer variants."""
    variants = {answer.lower().strip()}
    
    # Add singular/plural variants
    if answer.endswith('s'):
        variants.add(answer[:-1])
    else:
        variants.add(answer + 's')
        
    # Add variants without articles
    if answer.startswith('the '):
        variants.add(answer[4:])
        
    # Add variants without punctuation
    no_punct = re.sub(r'[^\w\s]', '', answer)
    variants.add(no_punct)
    
    # Add hyphenated/non-hyphenated variants
    if '-' in answer:
        variants.add(answer.replace('-', ' '))
    elif ' ' in answer:
        variants.add(answer.replace(' ', '-'))
        
    # Add common abbreviations for long words
    if 'mount ' in answer:
        variants.add(answer.replace('mount ', 'mt '))
    if 'saint ' in answer:
        variants.add(answer.replace('saint ', 'st '))
        
    # Handle articles and possessives
    variants.add(answer.replace("'s", ""))
    for article in ['the ', 'a ', 'an ']:
        if answer.startswith(article):
            variants.add(answer[len(article):])
    
    # Handle special characters
    variants.add(answer.replace('&', 'and'))
    variants.add(answer.replace('and', '&'))
    
    # Handle numbers
    if answer.replace(',', '').replace('.', '').isdigit():
        num = float(answer.replace(',', ''))
        variants.add(f"{num:,.0f}")  # With commas
        variants.add(f"{num:.0f}")   # Without commas
        
    return variants