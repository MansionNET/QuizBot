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

        # Categories with specific descriptions and rules
        self.categories = [
            {
                "name": "science",
                "description": "Scientific concepts, discoveries, and phenomena across physics, chemistry, biology, and space.",
                "rules": [
                    "Use metric units only",
                    "Use full element names, not symbols",
                    "Cover diverse scientific fields",
                    "Include modern discoveries and breakthroughs",
                    "Focus on fascinating phenomena and concepts"
                ],
                "examples": [
                    {
                        "question": "Which element makes up 78% of Earth's atmosphere?",
                        "answer": "Nitrogen",
                        "fun_fact": "Despite being so abundant, nitrogen remained undiscovered until 1772 because it's colorless, odorless, and doesn't react easily with other elements."
                    }
                ]
            },
            {
                "name": "history",
                "description": "Historical events, figures, and cultural developments across different civilizations and eras.",
                "rules": [
                    "Cover diverse time periods and cultures",
                    "Include ancient to modern history",
                    "Focus on significant turning points",
                    "Highlight lesser-known but fascinating facts",
                    "Include cultural and social history"
                ],
                "examples": [
                    {
                        "question": "Which ancient wonder stood in Alexandria, Egypt?",
                        "answer": "Lighthouse",
                        "fun_fact": "The Lighthouse of Alexandria stood over 300 feet tall and used mirrors to reflect sunlight, visible from up to 34 miles away."
                    }
                ]
            },
            {
                "name": "geography",
                "description": "World geography, natural wonders, cities, and cultural landmarks.",
                "rules": [
                    "Mix physical and cultural geography",
                    "Include natural wonders and phenomena",
                    "Cover all continents and regions",
                    "Include interesting geographical features",
                    "Mix modern and historical geography"
                ],
                "examples": [
                    {
                        "question": "Which desert covers most of northern Africa?",
                        "answer": "Sahara",
                        "fun_fact": "The Sahara alternates between being a desert and a green savannah every 20,000 years due to Earth's axis wobble."
                    }
                ]
            },
            {
                "name": "entertainment",
                "description": "Movies, TV shows, actors, directors, and memorable moments in film and television.",
                "rules": [
                    "Cover different genres and eras",
                    "Include international cinema",
                    "Focus on significant achievements",
                    "Include interesting production facts",
                    "Mix classic and modern content"
                ],
                "examples": [
                    {
                        "question": "Who directed Jurassic Park?",
                        "answer": "Spielberg",
                        "fun_fact": "The T-Rex roar in Jurassic Park was created by mixing sounds from tigers, elephants, and alligators."
                    }
                ]
            },
            {
                "name": "music",
                "description": "Music across all genres, artists, albums, and musical history.",
                "rules": [
                    "Cover multiple genres and eras",
                    "Include international music",
                    "Mix mainstream and influential underground",
                    "Include interesting music history",
                    "Cover instruments and terminology"
                ],
                "examples": [
                    {
                        "question": "Which band released Dark Side of the Moon?",
                        "answer": "Pink Floyd",
                        "fun_fact": "Dark Side of the Moon spent a record-breaking 937 weeks on Billboard's top 200 albums chart."
                    }
                ]
            },
            {
                "name": "pop_culture",
                "description": "Contemporary culture, trends, social media, gaming, and modern phenomena.",
                "rules": [
                    "Focus on significant cultural moments",
                    "Include digital and gaming culture",
                    "Cover viral phenomena and trends",
                    "Include social media milestones",
                    "Mix entertainment and technology"
                ],
                "examples": [
                    {
                        "question": "Which game introduced Mario in 1981?",
                        "answer": "Donkey Kong",
                        "fun_fact": "Mario was named after Nintendo's warehouse landlord Mario Segale, and was originally called Jumpman."
                    }
                ]
            },
            {
                "name": "sports",
                "description": "Sports history, achievements, athletes, and memorable moments.",
                "rules": [
                    "Cover multiple sports and eras",
                    "Include international sports",
                    "Focus on significant achievements",
                    "Include Olympic history",
                    "Mix team and individual sports"
                ],
                "examples": [
                    {
                        "question": "Which country invented basketball?",
                        "answer": "Canada",
                        "fun_fact": "Basketball was invented by James Naismith in 1891 while teaching at the YMCA Training School in Massachusetts."
                    }
                ]
            },
            {
                "name": "technology",
                "description": "Tech innovations, companies, inventors, and digital milestones.",
                "rules": [
                    "Cover different tech domains",
                    "Include historical innovations",
                    "Focus on breakthrough moments",
                    "Include interesting development stories",
                    "Mix hardware and software topics"
                ],
                "examples": [
                    {
                        "question": "Who created Linux?",
                        "answer": "Linus Torvalds",
                        "fun_fact": "Linux was originally just a hobby project, and Torvalds thought it would never support anything bigger than an AT hard disk."
                    }
                ]
            }
        ]

        self._fill_task: Optional[asyncio.Task] = None
        self._running = False

    def _get_question_generation_prompt(self, category: Dict) -> List[Dict]:
        """Get the improved prompt for question generation."""
        base_prompt = (
            "You are a trivia question generator specializing in creating clear, unambiguous, and educational questions. "
            f"Generate engaging trivia questions in the category: {category['name']}.\n\n"
            f"Category focus: {category['description']}\n\n"
            "OUTPUT FORMAT:\n"
            "Generate questions in this exact format:\n"
            "1. [Question]?\nAnswer: [1-3 word answer]\nFun Fact: [interesting fact]\n\n"
            "ANSWER REQUIREMENTS:\n"
            "1. Answers must be 1-3 words maximum\n"
            "2. Answers should be specific and concrete (e.g., 'Napoleon' not 'a French emperor')\n"
            "3. For dates, use year only unless month is crucial\n"
            "4. For measurements, use metric units\n"
            "5. For chemical elements, use full name not symbol\n"
            "6. For people, either full name or commonly known surname\n\n"
            "QUESTION STRUCTURE RULES:\n"
            "1. Start with WHO, WHAT, WHERE, WHEN, WHICH, or IN WHAT\n"
            "2. Maximum 15 words per question\n"
            "3. Must be answerable with a single, specific answer\n"
            "4. Must end with a question mark\n"
            "5. Must not contain multiple clauses or conjunctions\n\n"
            "CONTENT RULES:\n"
            "1. Focus on factual, verifiable information\n"
            "2. Avoid subjective terms ('best', 'most famous', 'greatest')\n"
            "3. Avoid relative time references ('recent', 'modern', 'current')\n"
            "4. Include specific details that make the answer unambiguous\n"
            "5. Fun facts should provide additional context, not repeat the question\n\n"
        )

        category_specific = self._get_category_specific_prompt(category)

        return [
            {
                "role": "system",
                "content": base_prompt + category_specific
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
        """Generate category-specific prompt additions."""
        return f"""
CATEGORY: {category['name'].upper()}
FOCUS: {category['description']}

SPECIFIC RULES FOR THIS CATEGORY:
{chr(10).join(f"- {rule}" for rule in category['rules'])}

EXAMPLE FOR THIS CATEGORY:
Question: "{category['examples'][0]['question']}"
Answer: "{category['examples'][0]['answer']}"
Fun Fact: "{category['examples'][0]['fun_fact']}"

Remember:
1. Questions must be unambiguous
2. Answers must be specific
3. Fun facts should provide new information
"""

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
                    if unused < 15:
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

    async def _generate_batch(self, count: int) -> List[Dict[str, str]]:
        """Generate a batch of questions with balanced categories."""
        valid_questions = []
        questions_per_category = max(2, count // len(self.categories))
        
        # Shuffle categories to randomize order
        categories = list(self.categories)
        random.shuffle(categories)
        
        # Try to get questions from each category
        for category in categories:
            if len(valid_questions) >= count:
                break
                
            # Generate questions for this category
            category_questions = []
            messages = self._get_question_generation_prompt(category)
            
            for attempt in range(self.max_retries):
                try:
                    await self.rate_limiter.acquire()

                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            self.api_url,
                            headers=self.headers,
                            json={
                                "model": self.default_model,
                                "messages": messages,
                                "temperature": 0.8,  # Increased for more variety
                                "max_tokens": 1000,
                                "top_p": 0.9
                            },
                            timeout=self.default_timeout
                        )

                        if response.status_code != 200:
                            error_msg = f"Mistral API error: {response.text}"
                            logger.error(error_msg)
                            if attempt == self.max_retries - 1:
                                break
                            continue

                        data = response.json()
                        content = data['choices'][0]['message']['content']

                        # Clean and parse the response
                        questions = self._parse_response(content)
                        logger.info(f"Generated {len(questions)} questions for category: {category['name']}")
                        
                        for q in questions:
                            try:
                                # Validate the question
                                validation_issues = self.validator.validate_question(q)
                                errors = [i for i in validation_issues if i.severity == ValidationSeverity.ERROR]

                                if errors:
                                    logger.warning(f"Skipping invalid question due to: {errors}")
                                    continue

                                # Add category and normalize
                                q['category'] = category['name']
                                q = self._preprocess_question_answer(q)
                                q['id'] = str(uuid.uuid4())
                                logger.info(f"Processed question: {q['question']} (Answer: {q['answer']}, Category: {q['category']})")
                                
                                # Check for duplicates
                                question_text = q['question'].lower()
                                answer_text = q['answer'].lower()
                                is_duplicate = any(
                                    vq['question'].lower() == question_text or 
                                    vq['answer'].lower() == answer_text
                                    for vq in valid_questions
                                )
                                
                                if not is_duplicate:
                                    category_questions.append(q)
                                    logger.info(f"Added valid question for category {category['name']}")
                                    if len(category_questions) >= questions_per_category:
                                        break
                                else:
                                    logger.info(f"Skipping duplicate question: {q['question']}")

                            except ValueError as e:
                                logger.warning(f"Skipping invalid question: {e}")
                                
                        if category_questions:
                            valid_questions.extend(category_questions[:questions_per_category])
                            break

                except (httpx.TimeoutException, httpx.RequestError) as e:
                    error_msg = f"Mistral API request failed: {e}"
                    logger.error(error_msg)
                    if attempt == self.max_retries - 1:
                        break

                delay = self.base_retry_delay * (2 ** attempt) + (random.random() * 0.5)
                logger.info(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
                
        return valid_questions[:count]

    def _parse_response(self, content: str) -> List[Dict]:
        """Parse and clean the API response."""
        content = content.strip()
        questions = []
        
        # Split into individual questions (numbered format)
        question_texts = re.split(r'\d+\.\s+', content)[1:]  # Skip empty first split
        
        for text in question_texts:
            try:
                # Extract question, answer, and fun fact
                match = re.match(
                    r'(.*?)\s*Answer:\s*(.*?)\s*Fun Fact:\s*(.*?)(?:\s*\d+\.|$)',
                    text.strip(),
                    re.DOTALL
                )
                
                if match:
                    question, answer, fun_fact = match.groups()
                    questions.append({
                        "question": question.strip(),
                        "answer": answer.strip(),
                        "fun_fact": fun_fact.strip()
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to parse question: {text}")
                continue
                
        return questions

    def _preprocess_question_answer(self, question_data: Dict) -> Dict:
        """Preprocess and normalize question/answer data."""
        category = question_data.get('category', 'general')

        # Normalize the answer
        question_data['answer'] = self.normalizer.normalize_answer(
            question_data['answer'],
            category
        )

        # Generate answer variants
        question_data['answer_variants'] = create_answer_variants(
            question_data['answer']
        )

        return question_data
