"""Service for interacting with Mistral AI API."""
import logging
import json
import uuid
import httpx
import random
from typing import Dict, Optional, List
import asyncio
import time
import re
from utils.validators import QuestionValidator, ValidationSeverity
from utils.answer_normalizer import AnswerNormalizer, create_answer_variants

logger = logging.getLogger(__name__)

class TokenBucket:
    """Token bucket rate limiter implementation."""
    def __init__(self, tokens_per_second: float, max_tokens: int):
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            while self.tokens <= 0:
                now = time.time()
                time_passed = now - self.last_update
                self.tokens = min(
                    self.max_tokens,
                    self.tokens + time_passed * self.tokens_per_second
                )
                self.last_update = now
                if self.tokens <= 0:
                    await asyncio.sleep(1.0 / self.tokens_per_second)

            self.tokens -= 1
            self.last_update = time.time()

class MistralService:
    """Service for generating quiz questions using Mistral AI."""

    def __init__(self, api_key: str, database, min_questions: int = 30):
        self.api_key = api_key
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.reset_lock = asyncio.Lock()
        self.default_model = "mistral-tiny"
        self.default_timeout = 20.0
        self.max_retries = 5
        self.base_retry_delay = 2.0
        self.min_questions = min_questions
        self.database = database

        # Rate limiter: 0.5 requests per second, max burst of 5
        self.rate_limiter = TokenBucket(tokens_per_second=0.5, max_tokens=5)

        # Initialize utilities
        self.validator = QuestionValidator()
        self.normalizer = AnswerNormalizer()

        # Updated categories with more variety and better examples
        self.categories = [
            {
                "name": "geography",
                "description": "World geography, capitals, landmarks, and natural features",
                "rules": [
                    "Include specific locations and measurements",
                    "Mix physical and political geography",
                    "Cover all continents and regions",
                    "Include both natural and man-made features",
                    "Use official names for countries and cities"
                ],
                "examples": [
                    {
                        "question": "What's the smallest country in the world?",
                        "answer": "Vatican City",
                        "fun_fact": "Vatican City is only 0.44 square kilometers in size."
                    }
                ]
            },
            {
                "name": "history",
                "description": "Historical events, dates, figures, and civilizations",
                "rules": [
                    "Include specific dates for major events",
                    "Cover different time periods and cultures",
                    "Focus on significant historical moments",
                    "Include both ancient and modern history",
                    "Use commonly accepted historical facts"
                ],
                "examples": [
                    {
                        "question": "In what year did World War II end?",
                        "answer": "1945",
                        "fun_fact": "The official surrender ceremony lasted 23 minutes on the USS Missouri."
                    }
                ]
            },
            {
                "name": "science",
                "description": "Scientific facts, discoveries, and natural phenomena",
                "rules": [
                    "Use metric units for measurements",
                    "Include specific numbers and facts",
                    "Cover various scientific fields",
                    "Focus on verified scientific facts",
                    "Include interesting scientific phenomena"
                ],
                "examples": [
                    {
                        "question": "How many bones does an adult human have?",
                        "answer": "206",
                        "fun_fact": "Babies are born with about 300 bones, some of which fuse together as they grow."
                    }
                ]
            },
            {
                "name": "arts",
                "description": "Art, literature, music, and cultural achievements",
                "rules": [
                    "Include specific artists and works",
                    "Cover different art forms",
                    "Mix classical and modern art",
                    "Include international artists",
                    "Focus on significant works"
                ],
                "examples": [
                    {
                        "question": "Who painted The Starry Night?",
                        "answer": "Van Gogh",
                        "fun_fact": "Van Gogh painted The Starry Night while in an asylum in Saint-Rémy-de-Provence."
                    }
                ]
            },
            {
                "name": "entertainment",
                "description": "Movies, TV shows, celebrities, and popular culture",
                "rules": [
                    "Include specific titles and dates",
                    "Cover different genres and eras",
                    "Mix mainstream and classic content",
                    "Include international entertainment",
                    "Focus on verified facts"
                ],
                "examples": [
                    {
                        "question": "What's the highest-grossing film of all time?",
                        "answer": "Avatar",
                        "fun_fact": "Avatar took 15 years to make due to waiting for technology to catch up with Cameron's vision."
                    }
                ]
            },
            {
                "name": "sports",
                "description": "Sports history, rules, records, and athletes",
                "rules": [
                    "Include specific records and dates",
                    "Cover different sports",
                    "Mix team and individual sports",
                    "Include international sports",
                    "Focus on major achievements"
                ],
                "examples": [
                    {
                        "question": "How high is a regulation NBA basket?",
                        "answer": "10 feet",
                        "fun_fact": "The 10-foot height was established in 1891 and hasn't changed since."
                    }
                ]
            },
            {
                "name": "food_drink",
                "description": "Cuisine, beverages, and food culture worldwide",
                "rules": [
                    "Include specific ingredients and origins",
                    "Cover different cuisines",
                    "Mix traditional and modern food",
                    "Include cooking techniques",
                    "Focus on cultural significance"
                ],
                "examples": [
                    {
                        "question": "Which country drinks the most coffee per capita?",
                        "answer": "Finland",
                        "fun_fact": "The average Finn consumes about 12 kg of coffee per year."
                    }
                ]
            },
            {
                "name": "nature",
                "description": "Animals, plants, and natural phenomena",
                "rules": [
                    "Include specific species and facts",
                    "Cover different ecosystems",
                    "Mix common and unusual species",
                    "Include biological facts",
                    "Focus on unique characteristics"
                ],
                "examples": [
                    {
                        "question": "What is the fastest bird in the world?",
                        "answer": "Peregrine Falcon",
                        "fun_fact": "The Peregrine Falcon can reach speeds over 380 km/h during its hunting dive."
                    }
                ]
            }
        ]

        self._fill_task: Optional[asyncio.Task] = None
        self._running = False

    def _get_question_generation_prompt(self, category: Dict) -> List[Dict]:
        base_prompt = (
            "You are a trivia question generator specializing in creating clear, engaging, and factual questions. "
            f"Generate trivia questions in the category: {category['name']}.\n\n"
            "QUESTION RULES:\n"
            "1. Questions must be clear, direct, and have a single unambiguous answer\n"
            "2. Prefer simpler, well-known answers over obscure ones\n"
            "3. Questions should be interesting but not overly technical\n"
            "4. For dates, use simple years without 'CE/BCE' unless crucial\n"
            "5. Accept common variations of answers (e.g., 'Da Vinci' or 'Leonardo da Vinci')\n\n"
            "FORMAT RULES:\n"
            "1. Question format: 'What/Who/Where/When/Which/How many [rest of question]?'\n"
            "2. No trailing punctuation except the question mark\n"
            "3. Answer format: lowercase, 1-3 words, simplest correct form\n"
            "4. Fun fact must provide new interesting information\n\n"
            "EXAMPLES:\n"
            "Q: Who painted the Mona Lisa?\n"
            "A: da vinci\n"
            "Fun fact: The Mona Lisa was painted between 1503 and 1519 and is housed in the Louvre Museum.\n\n"
            "Q: What is the highest mountain on Earth?\n"
            "A: everest\n"
            "Fun fact: Mount Everest grows about 4 millimeters taller every year due to geological uplift.\n\n"
            "AVOID:\n"
            "1. Relative time references ('recent', 'modern', 'current')\n"
            "2. Subjective terms ('best', 'greatest', 'most famous')\n"
            "3. Multiple choice or true/false questions\n"
            "4. Compound questions using 'and' or 'or'\n"
            "5. Overly specific or technical answers\n"
        )

        return [
            {
                "role": "system",
                "content": base_prompt + self._get_category_specific_prompt(category)
            },
            {
                "role": "assistant",
                "content": json.dumps(category['examples'], indent=2)
            },
            {
                "role": "user",
                "content": f"Generate 5 high-quality {category['name']} questions following the format and rules exactly."
            }
        ]

    def _get_category_specific_prompt(self, category: Dict) -> str:
        """Generate category-specific prompt additions with improved specificity."""
        return f"""
CATEGORY GUIDELINES FOR {category['name'].upper()}:
Description: {category['description']}

SPECIFIC RULES:
{chr(10).join(f"- {rule}" for rule in category['rules'])}

EXAMPLE QUESTION:
Q: "{category['examples'][0]['question']}"
A: "{category['examples'][0]['answer']}"
Fun Fact: "{category['examples'][0]['fun_fact']}"

KEY REQUIREMENTS:
1. Questions must have unambiguous, verifiable answers
2. Answers must be widely accepted facts
3. Fun facts should provide additional context not mentioned in the question
4. Include specific dates, measurements, or numbers when relevant
5. Focus on interesting but not obscure information
"""

    async def _parse_response(self, content: str) -> List[Dict]:
        """Parse and clean the API response with improved handling."""
        questions = []
        
        # Split by question pattern
        question_blocks = re.split(r'\d+\.|\n{2,}', content)
        
        for block in question_blocks:
            block = block.strip()
            if not block:
                continue
                
            try:
                # Look for question-answer-fun fact pattern
                matches = re.match(
                    r'(?:Q:)?\s*(.+?)\s*(?:A:|Answer:)\s*(.+?)\s*(?:Fun Fact:|$)(.*)',
                    block,
                    re.DOTALL | re.IGNORECASE
                )
                
                if matches:
                    question, answer, fun_fact = matches.groups()
                    
                    # Clean up the extracted parts
                    question = question.strip().rstrip('?') + '?'
                    answer = answer.strip()
                    fun_fact = fun_fact.strip() if fun_fact else ""
                    
                    # Basic validation
                    if question and answer:
                        questions.append({
                            "question": question,
                            "answer": answer,
                            "fun_fact": fun_fact or f"Related to {question.lower().replace('?', '')}"
                        })
                
            except Exception as e:
                logger.warning(f"Failed to parse question block: {block[:100]}... Error: {str(e)}")
                continue
                
        return questions
    
    def _validate_and_clean_question(self, question_data: Dict) -> Optional[Dict]:
        """Validate and clean a question before adding to database."""
        try:
            # Basic structure validation
            if not all(k in question_data for k in ['question', 'answer', 'fun_fact']):
                return None

            question = question_data['question'].strip()
            answer = question_data['answer'].strip()
            fun_fact = question_data['fun_fact'].strip()

            # Question format validation
            if not question.endswith('?'):
                question += '?'
            
            # Answer format validation
            answer = re.sub(r'\s+', ' ', answer)  # Normalize whitespace
            
            # Fun fact validation - ensure it's not empty and different from question
            if not fun_fact or fun_fact.lower() in question.lower():
                fun_fact = f"Additional information about {answer}"

            # Return cleaned data
            return {
                "question": question,
                "answer": answer,
                "fun_fact": fun_fact,
                "category": question_data.get('category', 'general'),
                "difficulty": question_data.get('difficulty', 2)
            }
            
        except Exception as e:
            logger.warning(f"Question validation failed: {str(e)}")
            return None

    async def _generate_batch(self, count: int) -> List[Dict[str, str]]:
        """Generate a batch of questions with balanced categories."""
        valid_questions = []
        questions_per_category = max(2, count // len(self.categories))
        
        # Shuffle categories for variety
        categories = list(self.categories)
        random.shuffle(categories)
        
        for category in categories:
            if len(valid_questions) >= count:
                break
                
            category_questions = []
            for attempt in range(self.max_retries):
                try:
                    await self.rate_limiter.acquire()
                    messages = self._get_question_generation_prompt(category)
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            self.api_url,
                            headers=self.headers,
                            json={
                                "model": self.default_model,
                                "messages": messages,
                                "temperature": 0.8,
                                "max_tokens": 1000,
                                "top_p": 0.9
                            },
                            timeout=self.default_timeout
                        )

                        if response.status_code != 200:
                            logger.error(f"Mistral API error: {response.text}")
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(self.base_retry_delay * (2 ** attempt))
                            continue

                        data = response.json()
                        content = data['choices'][0]['message']['content']
                        
                        # Parse and validate questions
                        questions = await self._parse_response(content)
                        logger.info(f"Generated {len(questions)} questions for category: {category['name']}")
                        
                        for q in questions:
                            try:
                                # Validate the question
                                validation_issues = self.validator.validate_question(q)
                                errors = [i for i in validation_issues if i.severity == ValidationSeverity.ERROR]

                                if errors:
                                    logger.warning(f"Skipping invalid question due to: {errors}")
                                    continue

                                # Clean and normalize the question
                                cleaned_question = self._validate_and_clean_question(q)
                                if not cleaned_question:
                                    continue

                                # Add category and generate ID
                                cleaned_question['category'] = category['name']
                                cleaned_question['id'] = str(uuid.uuid4())
                                
                                # Add answer variants
                                cleaned_question['answer'] = self.normalizer.normalize_answer(
                                    cleaned_question['answer'],
                                    category['name']
                                )
                                cleaned_question['answer_variants'] = create_answer_variants(
                                    cleaned_question['answer']
                                )

                                # Check for duplicates
                                is_duplicate = any(
                                    vq['question'].lower() == cleaned_question['question'].lower() or 
                                    vq['answer'].lower() == cleaned_question['answer'].lower()
                                    for vq in valid_questions + category_questions
                                )
                                
                                if not is_duplicate:
                                    category_questions.append(cleaned_question)
                                    if len(category_questions) >= questions_per_category:
                                        break

                            except Exception as e:
                                logger.warning(f"Failed to process question: {str(e)}")
                                continue

                        if category_questions:
                            valid_questions.extend(category_questions[:questions_per_category])
                            break

                except Exception as e:
                    logger.error(f"Batch generation error: {str(e)}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.base_retry_delay * (2 ** attempt))
                    continue

        return valid_questions[:count]
    
    async def start(self):
        """Start the service and ensure minimum questions available."""
        logger.info("Starting Mistral service...")

        async with self.reset_lock:
            total = await self.database.count_questions()
            unused = await self.database.count_questions(unused_only=True)
            logger.info(f"Current questions in database: {total} total, {unused} unused")

            if total > 0 and unused == 0:
                logger.info("Resetting all questions to unused")
                await self.database.reset_used_questions()
                unused = total

            if unused < self.min_questions:
                logger.info("Generating initial batch of questions...")
                questions = await self._generate_batch(10)
                if questions:
                    added = await self.database.add_questions(questions)
                    logger.info(f"Added {added} questions to database")

        self._running = True
        self._fill_task = asyncio.create_task(self._fill_loop())
        logger.info("Question fill task started")

    async def stop(self):
        """Stop the service and cleanup."""
        logger.info("Stopping Mistral service...")
        self._running = False
        if self._fill_task:
            self._fill_task.cancel()

    async def generate_question(self) -> Optional[Dict[str, str]]:
        """Get a question from the database, generating new ones if needed."""
        question = await self.database.get_unused_question()
        if question:
            return question

        async with self.reset_lock:
            question = await self.database.get_unused_question()
            if question:
                return question

            logger.info("No unused questions, resetting used status")
            await self.database.reset_used_questions()
            question = await self.database.get_unused_question()
            if question:
                return question

            logger.warning("No questions available after reset, generating new batch...")
            questions = await self._generate_batch(5)
            if questions:
                await self.database.add_questions(questions)
                question = await self.database.get_unused_question()
                if question:
                    return question

            logger.error("Failed to get or generate any questions")
            return None

    async def _fill_loop(self):
        """Background loop to keep database filled with questions."""
        while self._running:
            try:
                async with self.reset_lock:
                    unused = await self.database.count_questions(unused_only=True)
                    if unused < self.min_questions:
                        logger.info(f"Generating more questions (currently {unused} unused)")
                        questions = await self._generate_batch(10)
                        if questions:
                            added = await self.database.add_questions(questions)
                            if added > 0:
                                logger.info(f"Added {added} new questions to database")
                                await asyncio.sleep(5)
                            else:
                                await asyncio.sleep(30)
                        else:
                            await asyncio.sleep(30)
                    else:
                        await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in question fill loop: {e}")
                await asyncio.sleep(30)

    def _preprocess_question_answer(self, question_data: Dict) -> Dict:
        """Preprocess and normalize question/answer data."""
        # Normalize answer format
        answer = question_data['answer'].strip().lower()
        
        # Handle numerical answers
        if answer.replace('.', '').isdigit():
            answer = '{:,}'.format(float(answer))
        
        # Handle multiple word answers
        answer = ' '.join(answer.split())
        
        # Add category and difficulty if not present
        question_data['category'] = question_data.get('category', 'general')
        question_data['difficulty'] = question_data.get('difficulty', 2)
        
        # Update the answer
        question_data['answer'] = answer
        
        # Generate answer variants
        question_data['answer_variants'] = create_answer_variants(answer)
        
        return question_data