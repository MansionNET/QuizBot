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
        self.default_timeout = 20.0
        self.max_retries = 5
        self.base_retry_delay = 2.0
        self.min_questions = min_questions
        self.database = database
        
        # Rate limiter: 0.5 requests per second, max burst of 5
        self.rate_limiter = TokenBucket(tokens_per_second=0.5, max_tokens=5)
        
        # Categories with specific descriptions for better question generation
        self.categories = [
            {
                "name": "science",
                "description": "Focus on fundamental scientific concepts, discoveries, and scientists. Include physics, chemistry, and general science."
            },
            {
                "name": "pop_science",
                "description": "Recent scientific discoveries, space missions, tech breakthroughs, and viral science news from the last decade."
            },
            {
                "name": "history",
                "description": "Major historical events, ancient civilizations, important dates, and significant historical figures."
            },
            {
                "name": "geography",
                "description": "Countries, capitals, major landmarks, rivers, mountains, and geographical features."
            },
            {
                "name": "biology",
                "description": "Human body, animals, plants, ecosystems, and biological processes."
            },
            {
                "name": "music",
                "description": "Famous musicians, bands, albums, songs, and music history across different genres."
            },
            {
                "name": "film",
                "description": "Classic movies, directors, actors, awards, and significant films from different decades."
            },
            {
                "name": "general",
                "description": "Interesting facts about everyday life, popular culture, world records, and miscellaneous trivia."
            }
        ]
        
        self._fill_task: Optional[asyncio.Task] = None
        self._running = False
        
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
        # Example questions showing the desired format and style
        example = [
            {
                "id": "q1",
                "category": "science",
                "difficulty": 2,
                "question": "Which chemical element has the symbol 'Au'?",
                "answer": "gold",
                "fun_fact": "The symbol Au comes from the Latin word for gold, 'aurum'."
            },
            {
                "id": "q2",
                "category": "geography",
                "difficulty": 1,
                "question": "What is the capital of France?",
                "answer": "Paris",
                "fun_fact": "Paris was founded in the 3rd century BC by a Celtic tribe called the Parisii."
            }
        ]
        
        # Select a random category for this batch
        category = random.choice(self.categories)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trivia question generator that outputs ONLY a valid JSON array. "
                    f"Generate {min(count, 5)} diverse trivia questions in the category: {category['name']}.\n\n"
                    f"Category description: {category['description']}\n\n"
                    "CRITICAL JSON FORMATTING RULES:\n"
                    "1. Use SINGLE quotes for values, never double quotes around already quoted values\n"
                    "2. No comments or extra text outside the JSON array\n"
                    "3. No trailing commas\n"
                    "4. Numbers should be unquoted numeric values\n"
                    "5. Follow this exact format for each question:\n"
                    "   {\n"
                    "     'id': 'q1',\n"
                    "     'category': 'science',\n" 
                    "     'difficulty': 2,\n"
                    "     'question': 'What is...?',\n"
                    "     'answer': 'answer',\n"
                    "     'fun_fact': 'interesting fact'\n"
                    "   }\n\n"
                    "CRITICAL QUESTION RULES:\n"
                    "1. Answers MUST be 1-3 words maximum\n"
                    "2. Questions must NOT contain their own answers\n"
                    "3. Questions must have exactly ONE correct answer\n"
                    "4. Questions should be clear and unambiguous\n"
                    "5. Avoid questions that could have multiple interpretations\n"
                    "6. Use specific dates, names, and facts\n"
                    "7. Questions should be engaging and educational\n\n"
                    "BAD EXAMPLES (DO NOT USE):\n"
                    "- 'The Mona Lisa is painted by which artist?' (contains answer)\n"
                    "- 'What could cause a rainbow?' (multiple possible answers)\n"
                    "- 'Name a US president' (multiple possible answers)\n"
                    "- 'Which scientist developed relativity?' (too vague)\n\n"
                    "GOOD EXAMPLES (USE THIS STYLE):\n"
                    "- 'Which Italian artist painted The Last Supper?'\n"
                    "- 'What atmospheric phenomenon causes a rainbow?'\n"
                    "- 'Who was the first US president?'\n"
                    "- 'Who published the Special Theory of Relativity in 1905?'\n\n"
                    "Return ONLY a JSON array like this - no other text:\n"
                    f"{json.dumps(example, indent=2)}"
                )
            },
            {
                "role": "user",
                "content": f"Generate {min(count, 5)} {category['name']} trivia questions following the rules exactly."
            }
        ]
        
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
                    logger.debug(f"Raw Mistral response: {content}")
                    
                    # Clean and parse the response
                    content = content.strip()
                    
                    # Remove comments (both // and /* */ style)
                    import re
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
                    
                    logger.debug(f"Cleaned content: {content}")
                    
                    try:
                        # Try to parse the JSON
                        questions = json.loads(content)
                        if not isinstance(questions, list):
                            questions = [questions]
                        response_data = {"questions": questions}
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error: {str(e)}")
                        logger.error(f"Raw content: {data['choices'][0]['message']['content']}")
                        logger.error(f"Cleaned content: {content}")
                        
                        # Try to fix common JSON issues
                        try:
                            # Remove any BOM or invisible characters
                            content = content.encode('ascii', 'ignore').decode()
                            
                            # Fix extra quotes around values
                            content = re.sub(r'"([^"]*)"([^"]*)"([^"]*)"', r'"\1\2\3"', content)
                            
                            # Fix missing quotes around numeric values
                            content = re.sub(r':\s*(\d+)([,}])', r': "\1"\2', content)
                            
                            # Try parsing again
                            questions = json.loads(content)
                            if not isinstance(questions, list):
                                questions = [questions]
                            response_data = {"questions": questions}
                            logger.info("Successfully recovered from JSON parse error")
                        except Exception as recovery_error:
                            logger.error(f"Failed to recover from JSON error: {recovery_error}")
                            raise e
                    
                    if isinstance(response_data, dict) and 'questions' in response_data:
                        questions = response_data['questions']
                    elif isinstance(response_data, list):
                        questions = response_data
                    else:
                        raise ValueError("Invalid response format")
                    
                    valid_questions = []
                    used_ids = set()
                    for q in questions:
                        try:
                            self._validate_question_data(q)
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
        
    def _validate_question_data(self, data: Dict[str, str]):
        """Validate the question data format and content."""
        required_keys = {"question", "answer", "fun_fact"}
        missing_keys = required_keys - set(data.keys())
        
        if missing_keys:
            raise ValueError(f"Missing required keys in question data: {missing_keys}")
        
        # Validate content existence
        if not data["question"].strip():
            raise ValueError("Question cannot be empty")
        if not data["answer"].strip():
            raise ValueError("Answer cannot be empty")
        if not data["fun_fact"].strip():
            raise ValueError("Fun fact cannot be empty")
        
        # Validate question quality
        question = data["question"].lower()
        answer = data["answer"].lower()
        
        # Check answer length (1-3 words)
        answer_words = answer.split()
        if len(answer_words) > 3:
            raise ValueError(f"Answer too long ({len(answer_words)} words): {answer}")
        
        # Check if answer appears in question
        if answer in question:
            raise ValueError("Question contains its own answer")
            
        # Check for answer words in question
        for word in answer_words:
            if len(word) > 3 and word in question:  # Only check words longer than 3 chars to avoid common words
                raise ValueError(f"Question contains answer word: {word}")
        
        # Check for vague or multiple-answer indicators
        vague_patterns = [
            "name a", "name any", "give an example", "give me an example",
            "what are some", "what could", "which of these", "such as",
            "for example", "like a", "one of the"
        ]
        
        for pattern in vague_patterns:
            if pattern in question:
                raise ValueError(f"Question contains vague pattern: {pattern}")
        
        # Check minimum lengths
        if len(question) < 15:
            raise ValueError("Question is too short")
        if len(answer) < 2:
            raise ValueError("Answer is too short")
        if len(data["fun_fact"]) < 20:
            raise ValueError("Fun fact is too short")
            
        # Check for proper question structure
        if not any(question.startswith(w) for w in ["what", "who", "where", "when", "which", "how", "why"]):
            raise ValueError("Question doesn't start with a question word")
            
        if not question.endswith("?"):
            raise ValueError("Question doesn't end with a question mark")
            
        # Check for overly complex questions
        if len(question.split()) > 20:
            raise ValueError("Question is too long/complex")
            
        # Additional pattern checks for common issues
        problematic_patterns = [
            ("or", "Question suggests multiple choice"),
            ("either", "Question suggests multiple choice"),
            ("following", "Question may be listing options"),
            ("choose", "Question suggests multiple choice")
        ]
        
        # Safe phrases that make these patterns okay
        safe_contexts = {
            "and": ["and the", "and in", "and at", "and by", "and during"],
            "or": ["or more", "or less", "or later", "or earlier"],
            "these": ["of these", "at these", "in these", "by these"]
        }
        
        for pattern, error in problematic_patterns:
            pattern_word = pattern.lower()
            if pattern_word in question.split() and not any(
                safe_phrase in question.lower() 
                for safe_phrase in safe_contexts.get(pattern_word, [])
            ):
                raise ValueError(error)
                
        return True  # If all validations pass
