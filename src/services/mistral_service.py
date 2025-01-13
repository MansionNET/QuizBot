"""Service for interacting with Mistral AI API."""
import logging
import json
import uuid
import httpx
import random
from typing import Dict, Optional, List
import asyncio
import time

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
        self.default_timeout = 20.0  # Increased timeout for larger batches
        self.max_retries = 5
        self.base_retry_delay = 2.0
        self.min_questions = min_questions
        self.database = database
        
        # Rate limiter: 0.5 requests per second (1 request per 2 seconds), max burst of 5
        self.rate_limiter = TokenBucket(tokens_per_second=0.5, max_tokens=5)
        
        # Categories for questions
        self.categories = [
            "science", "history", "geography", "arts", "sports",
            "technology", "nature", "space", "literature", "music"
        ]
        
        # Background task for filling questions
        self._fill_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the service and ensure minimum questions available."""
        logger.info("Starting Mistral service...")
        
        async with self.reset_lock:
            # Check current question count
            total = await self.database.count_questions()
            unused = await self.database.count_questions(unused_only=True)
            logger.info(f"Current questions in database: {total} total, {unused} unused")
            
            # Reset all questions to unused if needed
            if total > 0 and unused == 0:
                logger.info("Resetting all questions to unused")
                await self.database.reset_used_questions()
                unused = total
            
            # Generate initial batch if needed
            if unused < self.min_questions:
                logger.info("Generating initial batch of questions...")
                questions = await self._generate_batch(10)  # Larger initial batch
                if questions:
                    added = await self.database.add_questions(questions)
                    logger.info(f"Added {added} questions to database")
        
        # Start background fill task
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
        # Try to get unused question first
        question = await self.database.get_unused_question()
        if question:
            return question
            
        # If no unused questions, acquire lock before resetting
        async with self.reset_lock:
            # Check again in case another request just reset
            question = await self.database.get_unused_question()
            if question:
                return question
                
            # Reset questions and try one more time
            logger.info("No unused questions, resetting used status")
            await self.database.reset_used_questions()
            question = await self.database.get_unused_question()
            if question:
                return question
                
            # If still no questions after reset, generate new ones
            logger.warning("No questions available after reset, generating new batch...")
            questions = await self._generate_batch(5)  # Generate a batch instead of just one
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
                    # Start generating when we drop below 15 questions
                    unused = await self.database.count_questions(unused_only=True)
                    if unused < 15:
                        logger.info(f"Generating more questions (currently {unused} unused)")
                        
                        # Generate batch of 10 questions
                        questions = await self._generate_batch(10)
                        if questions:
                            added = await self.database.add_questions(questions)
                            if added > 0:
                                logger.info(f"Added {added} new questions to database")
                                await asyncio.sleep(5)  # Short sleep on success
                            else:
                                await asyncio.sleep(30)  # Longer sleep if no new questions added
                        else:
                            await asyncio.sleep(30)  # Longer sleep on failure
                    else:
                        # Sleep longer when we have enough questions
                        await asyncio.sleep(60)
                    
            except Exception as e:
                logger.error(f"Error in question fill loop: {e}")
                await asyncio.sleep(30)
        
    async def _generate_batch(self, count: int) -> List[Dict[str, str]]:
        """Generate a batch of questions."""
        # Example format with categories and difficulty, now with unique IDs
        example = [
            {
                "id": "q1",  # First question example
                "category": "science",
                "difficulty": 2,
                "question": "What is the hardest natural substance on Earth?",
                "answer": "diamond",
                "fun_fact": "Diamonds are made of pure carbon atoms arranged in a crystal structure."
            },
            {
                "id": "q2",  # Second question example to show ID progression
                "category": "science",
                "difficulty": 1,
                "question": "Which force pulls objects towards Earth?",
                "answer": "gravity",
                "fun_fact": "Gravity is the weakest of the four fundamental forces of nature."
            }
        ]
        
        # Select random category for this batch
        category = random.choice(self.categories)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trivia question generator that outputs ONLY a JSON array. Generate "
                    f"{min(count, 5)} diverse trivia questions in the category: {category}.\n\n"
                    "IMPORTANT: Return ONLY a JSON array like this - no other text:\n"
                    f"{json.dumps(example, indent=2)}\n\n"
                    "Each question must have:\n"
                    "- id (MUST be unique: q1, q2, q3, etc - increment for each question)\n"
                    "- category (the given category)\n"
                    "- difficulty (1=easy, 2=medium, 3=hard)\n"
                    "- question (the actual question)\n"
                    "- answer (single word or short phrase)\n"
                    "- fun_fact (interesting fact)\n\n"
                    "Format: Return ONLY the JSON array with proper commas between objects and properties.\n"
                    "IMPORTANT: Each question MUST have a different id (q1, q2, q3, etc)."
                )
            },
            {
                "role": "user",
                "content": f"Generate {min(count, 5)} {category} trivia questions in valid JSON format. Make sure each question has a unique ID (q1, q2, q3, etc)."
            }
        ]
        
        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit token
                await self.rate_limiter.acquire()
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.api_url,
                        headers=self.headers,
                        json={
                            "model": self.default_model,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": 1000,  # Increased token limit for better completion
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
                        
                    try:
                        data = response.json()
                        content = data['choices'][0]['message']['content']
                        # Log raw content for debugging
                        logger.debug(f"Raw Mistral response: {content}")
                        
                        # Clean and normalize content
                        content = content.strip()
                        content = ''.join(char for char in content if ord(char) >= 32)
                        
                        # Remove any existing escapes and normalize
                        content = content.replace('\\"', '"').replace('\\\\', '\\')
                        
                        import re
                        
                        # Extract just the array part if nested in questions object
                        array_match = re.search(r'\[\s*{\s*"id".*}\s*\]', content, re.DOTALL)
                        if array_match:
                            content = array_match.group(0)
                        
                        # Add missing commas between properties and objects
                        content = re.sub(r'"\s+"', '", "', content)  # Between properties
                        content = re.sub(r'}\s*{', '}, {', content)  # Between objects
                        content = re.sub(r'(\d)\s+"', r'\1, "', content)  # After numbers
                        
                        # Clean up formatting
                        content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                        content = content.replace(',,', ',')  # Remove double commas
                        
                        logger.debug(f"Cleaned content: {content}")
                        
                        # Parse the array
                        try:
                            questions = json.loads(content)
                            if not isinstance(questions, list):
                                questions = [questions]
                            response_data = {"questions": questions}
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON parse error: {e}")
                            logger.error(f"Cleaned content: {content}")
                            raise
                        
                        # Extract questions array
                        if isinstance(response_data, dict) and 'questions' in response_data:
                            questions = response_data['questions']
                        elif isinstance(response_data, list):
                            questions = response_data
                        else:
                            raise ValueError("Invalid response format")
                        
                        # Validate and ensure IDs are unique using timestamp-based UUIDs
                        valid_questions = []
                        used_ids = set()
                        for q in questions:
                            try:
                                self._validate_question_data(q)
                                # Always generate a new unique ID
                                q['id'] = str(uuid.uuid4())
                                valid_questions.append(q)
                            except ValueError as e:
                                logger.warning(f"Skipping invalid question: {e}")
                                
                        return valid_questions
                        
                    except (json.JSONDecodeError, KeyError) as e:
                        error_msg = f"Error parsing Mistral response: {e}"
                        logger.error(error_msg)
                        if attempt == self.max_retries - 1:
                            raise Exception(error_msg)
                            
            except (httpx.TimeoutException, httpx.RequestError) as e:
                error_msg = f"Mistral API request failed: {e}"
                logger.error(error_msg)
                if attempt == self.max_retries - 1:
                    raise Exception(error_msg)
                    
            # Exponential backoff with jitter
            delay = self.base_retry_delay * (2 ** attempt) + (random.random() * 0.5)
            logger.info(f"Retrying in {delay:.2f} seconds...")
            await asyncio.sleep(delay)
            
        return []
        
    def _validate_question_data(self, data: Dict[str, str]):
        """Validate the question data format."""
        required_keys = {"question", "answer", "fun_fact"}
        missing_keys = required_keys - set(data.keys())
        
        if missing_keys:
            raise ValueError(f"Missing required keys in question data: {missing_keys}")
            
        # Validate content
        if not data["question"].strip():
            raise ValueError("Question cannot be empty")
        if not data["answer"].strip():
            raise ValueError("Answer cannot be empty")
        if not data["fun_fact"].strip():
            raise ValueError("Fun fact cannot be empty")
            
        # Basic content validation
        if len(data["question"]) < 10:
            raise ValueError("Question is too short")
        if len(data["answer"]) < 1:
            raise ValueError("Answer is too short")
        if len(data["fun_fact"]) < 10:
            raise ValueError("Fun fact is too short")