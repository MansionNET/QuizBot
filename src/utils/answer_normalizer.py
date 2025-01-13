"""Answer normalization utilities for quiz questions."""
from typing import Dict, Optional, Set
import re
from datetime import datetime

class AnswerNormalizer:
    """Normalize answers to consistent formats."""
    
    def __init__(self):
        self.month_names = {
            'january': '01', 'february': '02', 'march': '03',
            'april': '04', 'may': '05', 'june': '06',
            'july': '07', 'august': '08', 'september': '09',
            'october': '10', 'november': '11', 'december': '12'
        }
        
        # Common unit conversions (to metric)
        self.unit_conversions = {
            'inch': 'centimeter',
            'inches': 'centimeters',
            'foot': 'meter',
            'feet': 'meters',
            'mile': 'kilometer',
            'miles': 'kilometers',
            'pound': 'kilogram',
            'pounds': 'kilograms',
            'fahrenheit': 'celsius'
        }
        
        # Common element symbols to full names
        self.element_symbols = {
            'H': 'hydrogen', 'He': 'helium', 'Li': 'lithium',
            'Be': 'beryllium', 'B': 'boron', 'C': 'carbon',
            'N': 'nitrogen', 'O': 'oxygen', 'F': 'fluorine',
            'Ne': 'neon', 'Na': 'sodium', 'Mg': 'magnesium',
            'Al': 'aluminum', 'Si': 'silicon', 'P': 'phosphorus',
            'S': 'sulfur', 'Cl': 'chlorine', 'Ar': 'argon',
            'K': 'potassium', 'Ca': 'calcium', 'Fe': 'iron',
            'Au': 'gold', 'Ag': 'silver', 'Cu': 'copper',
            'Zn': 'zinc', 'Pb': 'lead', 'Hg': 'mercury',
            'U': 'uranium'
        }
        
        # Common name variations
        self.name_variations = {
            'albert einstein': 'einstein',
            'isaac newton': 'newton',
            'charles darwin': 'darwin',
            'william shakespeare': 'shakespeare',
            'leonardo da vinci': 'da vinci',
            'michelangelo': 'michelangelo buonarroti',
            'pablo picasso': 'picasso',
            'vincent van gogh': 'van gogh',
            'claude monet': 'monet',
            'wolfgang amadeus mozart': 'mozart',
            'ludwig van beethoven': 'beethoven',
            'johann sebastian bach': 'bach'
        }

    def normalize_answer(self, answer: str, category: str) -> str:
        """Normalize an answer based on its category."""
        answer = answer.lower().strip()
        
        if category == 'science':
            return self._normalize_science_answer(answer)
        elif category == 'history':
            return self._normalize_history_answer(answer)
        elif category == 'geography':
            return self._normalize_geography_answer(answer)
        elif category == 'music':
            return self._normalize_music_answer(answer)
        
        return answer

    def _normalize_science_answer(self, answer: str) -> str:
        """Normalize scientific answers."""
        # Convert element symbols to full names
        for symbol, name in self.element_symbols.items():
            if answer.upper() == symbol:
                return name
            
        # Convert units to metric
        for imperial, metric in self.unit_conversions.items():
            if imperial in answer:
                return answer.replace(imperial, metric)
                
        # Remove special characters and standardize spacing
        answer = re.sub(r'[^\w\s-]', '', answer)
        return ' '.join(answer.split())

    def _normalize_history_answer(self, answer: str) -> str:
        """Normalize historical answers."""
        # Standardize dates
        date_match = re.search(r'(\d{1,4})\s*(AD|BC|CE|BCE)?', answer)
        if date_match:
            year = date_match.group(1)
            era = date_match.group(2) or 'CE'
            # Convert to 4-digit year where possible
            if len(year) <= 2:
                current_year = datetime.now().year
                century = current_year // 100
                year_num = int(year)
                if year_num > current_year % 100:
                    century -= 1
                year = f"{century}{year.zfill(2)}"
            return f"{year.zfill(4)} {era}"
            
        # Standardize name formats
        for full_name, preferred in self.name_variations.items():
            if answer in [full_name, preferred]:
                return preferred
                
        return answer

    def _normalize_geography_answer(self, answer: str) -> str:
        """Normalize geographical answers."""
        # Capitalize place names
        words = answer.split()
        if len(words) <= 3:  # Only capitalize if it's likely a proper name
            return ' '.join(word.capitalize() for word in words)
            
        return answer

    def _normalize_music_answer(self, answer: str) -> str:
        """Normalize music-related answers."""
        # Handle band name variations
        variations = {
            'the beatles': 'beatles',
            'pink floyd': 'pink floyd',
            'led zeppelin': 'led zeppelin',
            'rolling stones': 'rolling stones',
            'the rolling stones': 'rolling stones',
            'queen': 'queen',
            'the who': 'the who',
            'eagles': 'eagles',
            'the eagles': 'eagles'
        }
        
        if answer in variations:
            return variations[answer]
            
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
        
    return variants