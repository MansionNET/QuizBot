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
                "description": "Focus on fundamental scientific concepts, discoveries, and scientists.",
                "rules": [
                    "Use metric units only",
                    "Use full element names, not symbols",
                    "Include specific measurements where relevant",
                    "Use precise scientific terminology",
                    "Avoid theoretical or disputed concepts"
                ],
                "examples": [
                    {
                        "question": "What is the atomic number of carbon?",
                        "answer": "6",
                        "fun_fact": "Carbon forms the basis for all known life forms due to its ability to form multiple stable covalent bonds."
                    }
                ]
            },
            {
                "name": "history",
                "description": "Major historical events, figures, and discoveries.",
                "rules": [
                    "Use full years (YYYY format)",
                    "Specify BCE/CE for dates before 1000 CE",
                    "Use commonly known names for historical figures",
                    "Focus on verified historical facts",
                    "Include geographical context when relevant"
                ],
                "examples": [
                    {
                        "question": "In what year did Christopher Columbus reach America?",
                        "answer": "1492",
                        "fun_fact": "Columbus never realized he had discovered a new continent, believing until his death that he had reached Asia."
                    }
                ]
            },
            {
                "name": "geography",
                "description": "Physical geography, countries, capitals, and landmarks.",
                "rules": [
                    "Use current, officially recognized names",
                    "Include continent/region for lesser-known locations",
                    "Use metric measurements for distances/heights",
                    "Focus on permanent geographical features",
                    "Use proper capitalization for place names"
                ],
                "examples": [
                    {
                        "question": "Which African country has Cairo as its capital?",
                        "answer": "Egypt",
                        "fun_fact": "Cairo is the largest city in the Arab world, with over 20 million people in its metropolitan area."
                    }
                ]
            },
            {
                "name": "music",
                "description": "Classical and popular music, instruments, and theory.",
                "rules": [
                    "Use commonly known artist/band names",
                    "Include years for historical references",
                    "Specify music genres where relevant",
                    "Focus on significant achievements/works",
                    "Use standard musical terminology"
                ],
                "examples": [
                    {
                        "question": "Which composer wrote The Four Seasons?",
                        "answer": "Vivaldi",
                        "fun_fact": "Each concerto in The Four Seasons is accompanied by a sonnet, possibly written by Vivaldi himself."
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
            "ANSWER FORMAT REQUIREMENTS:\n"
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
                "content": f"Generate high-quality {category['name']} questions following the rules exactly."
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
        """Generate a batch of questions."""
        # Select a random category for this batch
        category = random.choice(self.categories)
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
                            "temperature": 0.7,
                            "max_tokens": 1000,
                            "top_p": 0.9
                        },
                        timeout=self.default_timeout
                    )

                    if response.status_code != 200:
                        error_msg = f"Mistral API error: {response.text}"
                        logger.error(error_msg)
                        if attempt == self.max_retries - 1:
                            raise Exception(error_msg)
                        continue

                    data = response.json()
                    content = data['choices'][0]['message']['content']

                    # Clean and parse the response
                    questions = self._parse_response(content)
                    valid_questions = []

                    for q in questions:
                        try:
                            # Validate the question
                            validation_issues = self.validator.validate_question(q)
                            errors = [i for i in validation_issues if i.severity == ValidationSeverity.ERROR]

                            if errors:
                                logger.warning(f"Skipping invalid question due to: {errors}")
                                continue

                            # Normalize the answer
                            q = self._preprocess_question_answer(q)

                            # Add unique ID
                            q['id'] = str(uuid.uuid4())
                            valid_questions.append(q)

                        except ValueError as e:
                            logger.warning(f"Skipping invalid question: {e}")

                    return valid_questions

            except (httpx.TimeoutException, httpx.RequestError) as e:
                error_msg = f"Mistral API request failed: {e}"
                logger.error(error_msg)
                if attempt == self.max_retries - 1:
                    raise Exception(error_msg)

            delay = self.base_retry_delay * (2 ** attempt) + (random.random() * 0.5)
            logger.info(f"Retrying in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

        return []

    def _parse_response(self, content: str) -> List[Dict]:
        """Parse and clean the API response."""
        content = content.strip()

        # Remove comments (both // and /* */ style)
        content = re.sub(r'//.*?(\n|$)', '', content)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

        # Extract JSON array if embedded in other text
        array_match = re.search(r'\[\s*{.*}\s*\]', content, re.DOTALL)
        if array_match:
            content = array_match.group(0)

        # Fix common JSON formatting issues
        content = re.sub(r',\s*}', '}', content)  # Remove trailing commas
        content = re.sub(r',\s*]', ']', content)  # Remove trailing commas in arrays
        content = re.sub(r'"\s*"([^"]+)"\s*"', r'"\1"', content)  # Fix double quoted values
        content = re.sub(r'"\s*:\s*"([^"]+)"\s*([,}])', r'": "\1"\2', content)  # Fix value quoting
        content = re.sub(r'([{,])\s*"?(\w+)"?\s*:', r'\1 "\2":', content)  # Fix key quoting

        # Normalize whitespace
        content = re.sub(r'\s+', ' ', content)

        try:
            questions = json.loads(content)
            if not isinstance(questions, list):
                questions = [questions]
            return questions
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Content: {content}")
            return []

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
