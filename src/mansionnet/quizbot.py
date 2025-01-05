#!/usr/bin/env python3
"""
MansionNet QuizBot
An IRC bot that provides engaging trivia games using the Mistral AI API with
improved scoring, question generation, and user experience.
"""

import socket
import ssl
import time
import json
import sqlite3
from datetime import datetime, timedelta
import requests
from collections import defaultdict, deque
from typing import Dict, Optional, List, Tuple, Set
import threading
import random
import logging
import os
import re
from dataclasses import dataclass, field

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quizbot.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class QuizState:
    """Represents the current state of a quiz game"""
    active: bool = False
    current_question: Optional[str] = None
    current_answer: Optional[str] = None
    question_time: Optional[datetime] = None
    scores: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    question_number: int = 0
    total_questions: int = 10
    answer_timeout: int = 30  # seconds to answer
    channel: Optional[str] = None
    timer: Optional[threading.Timer] = None
    used_questions: Set[str] = field(default_factory=set)
    question_verifications: Dict[str, str] = field(default_factory=dict)
    streak_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Enhanced categories focusing on common knowledge
    categories: Dict[str, List[str]] = field(default_factory=lambda: {
        "Pop Culture": [
            "Movies & TV", "Music", "Video Games", "Social Media",
            "Celebrities", "Recent Events", "Internet Culture"
        ],
        "Sports & Games": [
            "Football/Soccer", "Basketball", "Olympics", "Popular Athletes",
            "Gaming", "eSports", "Sports History"
        ],
        "Science & Tech": [
            "Everyday Science", "Modern Technology", "Space Exploration",
            "Famous Inventions", "Internet & Apps", "Gadgets"
        ],
        "History & Current Events": [
            "Modern History (1950+)", "Famous People", "Major Events",
            "Recent News", "Popular Movements"
        ],
        "General Knowledge": [
            "Food & Drink", "Countries & Cities", "Famous Landmarks",
            "Popular Brands", "Trending Topics"
        ]
    })

class QuizBot:
    def __init__(self):
        # Load API key
        self.api_key = self.load_api_key()
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY not found in .env file or environment variables")
            
        # IRC Configuration
        self.server = "irc.inthemansion.com"
        self.port = 6697
        self.nickname = "QuizBot"
        self.channels = ["#quiz", "#test_room"]
        
        # Quiz state
        self.quiz_state = QuizState()
        
        # Question difficulty levels
        self.difficulty_levels = {
            "easy": 0.6,    # 60% of questions
            "medium": 0.3,  # 30% of questions
            "hard": 0.1     # 10% of questions
        }
        
        # Enhanced bonus point rules
        self.bonus_rules = {
            'streak': {3: 1.5, 5: 2.0, 7: 2.5},  # Streak length: bonus multiplier
            'speed': {5: 1.5, 3: 2.0}            # Seconds remaining: bonus multiplier
        }
        
        # Question templates
        self.question_templates = {
            "multiple_choice": "Question: {question}\nChoices: A) {a} B) {b} C) {c} D) {d}",
            "true_false": "True or False: {statement}",
            "standard": "{question}"
        }
        
        # Initialize database
        self.init_database()
        
        # SSL Configuration
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def load_api_key(self) -> Optional[str]:
        """Load API key from .env file or environment"""
        try:
            api_key = os.getenv("MISTRAL_API_KEY")
            if api_key:
                return api_key
            
            with open('.env', 'r') as f:
                for line in f:
                    if line.startswith('MISTRAL_API_KEY='):
                        return line.split('=')[1].strip().strip("'").strip('"')
        except Exception as e:
            logging.error(f"Error loading API key: {str(e)}")
            return None

    def init_database(self):
        """Initialize SQLite database with improved schema"""
        try:
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                
                # Enhanced scores table with more statistics
                c.execute('''
                    CREATE TABLE IF NOT EXISTS scores (
                        username TEXT PRIMARY KEY,
                        total_score INTEGER DEFAULT 0,
                        games_played INTEGER DEFAULT 0,
                        correct_answers INTEGER DEFAULT 0,
                        fastest_answer REAL DEFAULT 0,
                        longest_streak INTEGER DEFAULT 0,
                        highest_score INTEGER DEFAULT 0,
                        last_played TIMESTAMP
                    )
                ''')
                
                # Enhanced question history with difficulty tracking
                c.execute('''
                    CREATE TABLE IF NOT EXISTS question_history (
                        question_hash TEXT PRIMARY KEY,
                        question TEXT,
                        answer TEXT,
                        category TEXT,
                        times_asked INTEGER DEFAULT 1,
                        times_answered_correctly INTEGER DEFAULT 0,
                        last_asked TIMESTAMP,
                        average_answer_time REAL DEFAULT 0
                    )
                ''')
                
                conn.commit()
                
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")
            raise

    def get_mistral_prompt(self, category: str, subcategory: str, difficulty: str) -> str:
        """Generate an improved prompt for Mistral AI"""
        return f"""Generate a {difficulty} trivia question about {subcategory} (category: {category}) following these STRICT rules:

        ESSENTIAL REQUIREMENTS:
        1. Question MUST be about widely known, mainstream topics
        2. Focus on popular topics from the last 30 years
        3. NO obscure facts or technical details
        4. Answer MUST be immediately recognizable to average people
        5. Answer MUST be 1-3 words maximum
        6. NO trick questions or complex wordplay
        7. NO specific dates (use "recently" or "in the 2020s" instead)
        8. Questions should be fun and engaging

        FORMAT RULES:
        - Question must be under 15 words
        - Answer should be COMMON KNOWLEDGE
        - Include a brief, interesting fact for after the answer
        
        GOOD EXAMPLES:
        "Which famous social media platform did Elon Musk rename to X?"
        "What popular game features characters building with blocks?"
        "Which streaming service produced Stranger Things?"

        BAD EXAMPLES (DO NOT USE):
        "Which ocean was declared a sanctuary in 2009?" (Too specific)
        "What gene was first edited in 2015?" (Too technical)
        "Who was the first South American astronaut?" (Too obscure)

        Format response EXACTLY as:
        Question: [your question]
        Answer: [simple answer in lowercase]
        Fun Fact: [brief interesting fact that adds context]"""

    def get_question_from_mistral(self) -> Tuple[str, str]:
        """Get an improved question from Mistral AI"""
        try:
            # Select difficulty based on weights
            difficulty = random.choices(
                list(self.difficulty_levels.keys()),
                list(self.difficulty_levels.values())
            )[0]

            # Select category with weighted probability
            main_category = random.choice(list(self.quiz_state.categories.keys()))
            subcategory = random.choice(self.quiz_state.categories[main_category])

            prompt = self.get_mistral_prompt(main_category, subcategory, difficulty)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "mistral-tiny",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 300
            }
            
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            
            parts = content.split('Question: ')[1].split('Answer:')
            question = parts[0].strip()
            answer_part = parts[1].split('Fun Fact:')
            answer = answer_part[0].strip().lower()
            fun_fact = answer_part[1].strip() if len(answer_part) > 1 else ""

            # Validate question quality
            if self.is_question_too_complex(question) or self.is_answer_too_obscure(answer):
                return self.get_question_from_mistral()  # Try again

            # Store the question
            question_hash = f"{question}:{answer}"
            if question_hash in self.quiz_state.used_questions:
                return self.get_question_from_mistral()
            
            self.quiz_state.used_questions.add(question_hash)
            self.quiz_state.question_verifications[question] = fun_fact
            
            # Update database
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO question_history 
                    (question_hash, question, answer, category, last_asked)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (question_hash, question, answer, f"{main_category}:{subcategory}"))
                conn.commit()
            
            return question, answer

        except Exception as e:
            logging.error(f"Error getting question from Mistral: {e}")
            # Enhanced fallback questions
            fallback_questions = [
                ("What social media app is known for short videos and dance trends?", "tiktok"),
                ("Which movie franchise features Iron Man and Captain America?", "marvel"),
                ("What gaming console is made by Sony?", "playstation"),
                ("Which team won the FIFA World Cup 2022?", "argentina"),
                ("What company makes the iPhone?", "apple"),
                ("Which messaging app uses a ghost as its logo?", "snapchat"),
                ("What game became famous for its Among Us collaborations?", "fortnite"),
                ("Which streaming platform is known for its red N logo?", "netflix"),
                ("What social media platform is known for tweets?", "twitter"),
                ("Which company owns Instagram and WhatsApp?", "meta")
            ]
            return random.choice(fallback_questions)

    def is_question_too_complex(self, question: str) -> bool:
        """Check if a question is too complex"""
        # Check word count
        if len(question.split()) > 15:
            return True
            
        # Check for specific dates
        if re.search(r'\b\d{4}\b', question):
            return True
            
        # Check for complex technical terms
        complex_terms = [
            'genome', 'algorithm', 'quantum', 'molecular', 'theorem',
            'coefficient', 'synthesis', 'paradigm', 'pursuant',
            'infrastructure', 'implementation', 'methodology'
        ]
        if any(term in question.lower() for term in complex_terms):
            return True
            
        return False

    def calculate_bonus_points(self, username: str, time_taken: int) -> float:
        """Calculate bonus points based on streaks and speed"""
        bonus = 1.0
        
        # Streak bonus
        streak = self.quiz_state.streak_counts[username]
        for streak_req, multiplier in self.bonus_rules['streak'].items():
            if streak >= streak_req:
                bonus *= multiplier
                break
        
        # Speed bonus
        seconds_remaining = self.quiz_state.answer_timeout - time_taken
        for time_threshold, multiplier in self.bonus_rules['speed'].items():
            if seconds_remaining >= time_threshold:
                bonus *= multiplier
                break
        
        return bonus

    def is_answer_too_obscure(self, answer: str) -> bool:
        """Check if an answer is too obscure"""
        # Check answer length (shouldn't be too long)
        if len(answer.split()) > 3:
            return True
            
        # Check for complex proper nouns
        if any(char.isupper() for char in answer[1:]):
            return True
            
        # Check for obscure formatting
        if re.search(r'[^a-zA-Z0-9\s]', answer):
            return True
            
        return False

    def format_question(self, question: str, question_number: int) -> str:
        """Format question with black background and orange text"""
        BOLD = '\x02'
        COLOR = '\x03'
        RESET = '\x0F'
        
        # Orange text (7) on black background (1)
        return f"{COLOR}07,01{BOLD}Question {question_number}/10:{RESET} {COLOR}07,01{question}{RESET}"

    def check_answer(self, username: str, answer: str) -> bool:
        """Enhanced answer checking with improved matching"""
        if not self.quiz_state.active or not self.quiz_state.current_answer:
            return False
            
        time_elapsed = (datetime.now() - self.quiz_state.question_time).seconds
        if time_elapsed > self.quiz_state.answer_timeout:
            return False
        
        # Normalize answers for comparison
        user_answer = ''.join(answer.lower().split())
        correct_answer = ''.join(self.quiz_state.current_answer.lower().split())
        
        # Enhanced answer matching
        is_correct = (
            user_answer == correct_answer or
            user_answer.replace(' ', '') == correct_answer.replace(' ', '') or
            user_answer.replace('the', '') == correct_answer.replace('the', '') or
            user_answer + 's' == correct_answer or
            user_answer == correct_answer + 's' or
            (len(user_answer) > 3 and (
                user_answer in correct_answer or 
                correct_answer in user_answer or
                self.levenshtein_distance(user_answer, correct_answer) <= 1
            ))
        )
        
        if is_correct:
            self.quiz_state.streak_counts[username] += 1
            bonus_multiplier = self.calculate_bonus_points(username, time_elapsed)
            
            # Award points based on speed and question difficulty
            base_points = max(1, int(10 * (1 - time_elapsed/self.quiz_state.answer_timeout)))
            if self.quiz_state.question_number <= 3:
                base_points = min(base_points, 5)  # Cap easy questions at 5 points
            elif self.quiz_state.question_number <= 7:
                base_points = min(base_points, 8)  # Cap medium questions at 8 points
            
            total_points = int(base_points * bonus_multiplier)
            self.quiz_state.scores[username] += total_points
            
            # Update database
            self.update_score(username, total_points, time_elapsed)
            
            # If bonus points were awarded, announce it
            if bonus_multiplier > 1:
                bonus_msg = f"{self.format_bonus_message(base_points, total_points, bonus_multiplier)}"
                self.send_channel_message(bonus_msg)
            
            return True
        else:
            self.quiz_state.streak_counts[username] = 0
            return False

    def levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate the Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]

    def format_bonus_message(self, base_points: int, total_points: int, multiplier: float) -> str:
        """Format bonus point message with colors"""
        BOLD = '\x02'
        COLOR = '\x03'
        RESET = '\x0F'
        YELLOW = '08'
        GREEN = '03'
        
        return (
            f"{COLOR}{YELLOW}🌟 Bonus x{multiplier:.1f}!{RESET} "
            f"{base_points} → {COLOR}{GREEN}{BOLD}{total_points}{RESET} points"
        )

    def update_score(self, username: str, points: int, answer_time: float):
        """Update user score with enhanced statistics"""
        try:
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                
                # Get current streak
                current_streak = self.quiz_state.streak_counts[username]
                
                c.execute('''
                    INSERT INTO scores (
                        username, total_score, games_played, correct_answers, 
                        fastest_answer, longest_streak, highest_score, last_played
                    )
                    VALUES (?, ?, 1, 1, ?, ?, ?, datetime('now'))
                    ON CONFLICT(username) DO UPDATE SET
                        total_score = total_score + ?,
                        correct_answers = correct_answers + 1,
                        fastest_answer = CASE 
                            WHEN fastest_answer = 0 OR ? < fastest_answer 
                            THEN ? 
                            ELSE fastest_answer 
                        END,
                        longest_streak = CASE
                            WHEN ? > longest_streak
                            THEN ?
                            ELSE longest_streak
                        END,
                        highest_score = CASE
                            WHEN ? > highest_score
                            THEN ?
                            ELSE highest_score
                        END,
                        last_played = datetime('now')
                ''', (
                    username, points, answer_time, current_streak, points,
                    points, answer_time, answer_time, current_streak, current_streak,
                    points, points
                ))
                conn.commit()
        except Exception as e:
            logging.error(f"Error updating score: {e}")

    def get_leaderboard(self) -> str:
        """Get enhanced leaderboard with detailed statistics"""
        try:
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                c.execute('''
                    SELECT 
                        username, total_score, correct_answers, fastest_answer,
                        longest_streak, highest_score
                    FROM scores 
                    ORDER BY total_score DESC 
                    LIMIT 5
                ''')
                leaders = c.fetchall()
            
            if not leaders:
                return "No scores yet! Start a quiz with !quiz"
            
            # IRC color codes
            BOLD = '\x02'
            COLOR = '\x03'
            RESET = '\x0F'
            GOLD = '07'
            SILVER = '14'
            BRONZE = '05'
            
            lines = [f"{COLOR}{GOLD}{BOLD}🏆 Top Quiz Masters 🏆{RESET}"]
            for i, (username, score, correct, fastest, streak, highest) in enumerate(leaders, 1):
                # Color medal based on position
                if i == 1:
                    medal = f"{COLOR}{GOLD}🥇{RESET}"
                elif i == 2:
                    medal = f"{COLOR}{SILVER}🥈{RESET}"
                elif i == 3:
                    medal = f"{COLOR}{BRONZE}🥉{RESET}"
                else:
                    medal = f"{COLOR}12•{RESET}"
                
                lines.append(
                    f"{medal} {BOLD}{username}{RESET}: {score} points "
                    f"({correct} correct, {fastest:.1f}s best, {streak}x streak)"
                )
            
            return " | ".join(lines)
            
        except Exception as e:
            logging.error(f"Error getting leaderboard: {e}")
            return "Error retrieving leaderboard"

    def handle_command(self, username: str, channel: str, message: str):
        """Handle bot commands with improved responses"""
        if message == "!help":
            help_messages = [
                f"{self.format_help_header('QuizBot Commands & Rules')}",
                "🎮 Commands:",
                "  !quiz - Start a new quiz game",
                "  !stats - View your detailed statistics",
                "  !leaderboard - Show top players",
                "  !stop - Stop current quiz (admin only)",
                "",
                "📋 How to Play:",
                "  • Each quiz has 10 questions",
                "  • 30 seconds to answer each question",
                "  • Type your answer directly in the channel",
                "  • Faster answers earn more points (1-10 base points)",
                "",
                "🌟 Bonus Points:",
                "  • Answer Streaks: 3x = 1.5x, 5x = 2x, 7x = 2.5x points",
                "  • Quick Answers: 5s left = 1.5x, 3s left = 2x points"
            ]
            
            for msg in help_messages:
                self.send_channel_message(msg)
                time.sleep(0.2)
            return

        if message == "!leaderboard":
            leaderboard = self.get_leaderboard()
            self.send(f"PRIVMSG {channel} :{leaderboard}")
            return

        if message == "!quiz":
            self.start_quiz(channel)
            return

        if message == "!stop":
            if username == "Avatar":  # Admin check
                self.end_quiz()
            else:
                self.send_channel_message(f"{username}: Only Avatar can stop the quiz")
            return

        if message == "!stats":
            stats = self.get_player_stats(username)
            self.send_channel_message(stats)
            return
                
        # Handle answer attempts during active quiz
        if self.quiz_state.active:
            if self.check_answer(username, message):
                verification = self.quiz_state.question_verifications.get(
                    self.quiz_state.current_question,
                    "Good job!"
                )
                self.send_channel_message(
                    f"✨ Correct, {username}! The answer was: {self.quiz_state.current_answer}\n"
                    f"💡 {verification}"
                )
                time.sleep(2)
                self.next_question()

    def format_help_header(self, text: str) -> str:
        """Format help header with colors"""
        BOLD = '\x02'
        COLOR = '\x03'
        RESET = '\x0F'
        BLUE = '12'
        
        return f"{COLOR}{BLUE}{BOLD}{'='*20} {text} {'='*20}{RESET}"

    def get_player_stats(self, username: str) -> str:
        """Get detailed player statistics with formatting"""
        try:
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                c.execute('''
                    SELECT 
                        total_score, games_played, correct_answers, fastest_answer,
                        longest_streak, highest_score
                    FROM scores WHERE username = ?
                ''', (username,))
                stats = c.fetchone()
                
                if not stats:
                    return f"No stats found for {username}"
                    
                score, games, correct, fastest, streak, highest = stats
                
                # Format stats with colors
                BOLD = '\x02'
                COLOR = '\x03'
                RESET = '\x0F'
                BLUE = '12'
                GREEN = '03'
                
                return (
                    f"{COLOR}{BLUE}{BOLD}Stats for {username}{RESET} | "
                    f"Total Score: {COLOR}{GREEN}{score}{RESET} | "
                    f"Games: {games} | "
                    f"Correct: {correct} | "
                    f"Best Time: {fastest:.1f}s | "
                    f"Best Streak: {streak}x | "
                    f"Highest Score: {highest} | "
                    f"Avg: {score/games:.1f} points/game"
                )
        except Exception as e:
            logging.error(f"Error getting player stats: {e}")
            return "Error retrieving stats"

    def next_question(self):
        """Progress to the next question with improved handling"""
        if not self.quiz_state.active:
            return
            
        # Cancel existing timer if any
        if self.quiz_state.timer:
            self.quiz_state.timer.cancel()
            
        self.quiz_state.question_number += 1
        if self.quiz_state.question_number > self.quiz_state.total_questions:
            self.end_quiz()
            return
            
        question, answer = self.get_question_from_mistral()
        self.quiz_state.current_question = question
        self.quiz_state.current_answer = answer
        self.quiz_state.question_time = datetime.now()
        
        # Format and send question
        formatted_question = self.format_question(question, self.quiz_state.question_number)
        self.send_channel_message(formatted_question)
        
        # Start answer timeout timer
        self.quiz_state.timer = threading.Timer(self.quiz_state.answer_timeout, self.handle_timeout)
        self.quiz_state.timer.start()

    def handle_timeout(self):
        """Handle question timeout with improved feedback"""
        if self.quiz_state.active and self.quiz_state.current_answer:
            verification = self.quiz_state.question_verifications.get(
                self.quiz_state.current_question,
                "Time's up!"
            )
            
            BOLD = '\x02'
            COLOR = '\x03'
            RESET = '\x0F'
            
            self.send_channel_message(
                f"{COLOR}01,07⏰ Time's up!{RESET} The answer was: "
                f"{COLOR}01,07{BOLD}{self.quiz_state.current_answer}{RESET}\n"
                f"💡 {verification}"
            )
            time.sleep(2)
            self.next_question()

    def start_quiz(self, channel: str):
        """Start a new quiz with improved welcome message"""
        if self.quiz_state.active:
            self.send_channel_message("A quiz is already in progress!")
            return
            
        self.quiz_state = QuizState()
        self.quiz_state.active = True
        self.quiz_state.channel = channel
        
        # Enhanced welcome message with colors
        BOLD = '\x02'
        COLOR = '\x03'
        RESET = '\x0F'
        BLUE = '12'
        GREEN = '03'
        YELLOW = '08'
        
        welcome_msg = [
            f"{COLOR}07,01{BOLD}🎯 New Quiz Starting!{RESET}",
            f"{COLOR}07,01• Type your answer in the channel{RESET}",
            f"{COLOR}07,01• Faster answers = More points{RESET}",
            f"{COLOR}07,01• Get bonus points for answer streaks{RESET}",
            f"{COLOR}07,01• {self.quiz_state.answer_timeout} seconds per question{RESET}",
            f"{COLOR}07,01• {self.quiz_state.total_questions} questions{RESET}",
            f"{COLOR}07,01Type !help for detailed rules{RESET}"
        ]
        
        for msg in welcome_msg:
            self.send_channel_message(msg)
            time.sleep(0.5)
            
        time.sleep(2)
        self.next_question()

    def end_quiz(self):
        """End the quiz with consistent formatting"""
        if not self.quiz_state.active:
            return
            
        self.quiz_state.active = False
        
        if self.quiz_state.timer:
            self.quiz_state.timer.cancel()
        
        final_scores = sorted(self.quiz_state.scores.items(), key=lambda x: x[1], reverse=True)
        if final_scores:
            COLOR = '\x03'
            RESET = '\x0F'
            
            self.send_channel_message(f"{COLOR}07,01Final Results{RESET}")
            time.sleep(0.2)
            
            for username, score in final_scores:
                self.send_channel_message(
                    f"{COLOR}07,01{username}: {score} points{RESET}"
                )
                time.sleep(0.2)
            
            # Update database
            with sqlite3.connect('quiz.db') as conn:
                c = conn.cursor()
                for username, _ in final_scores:
                    c.execute('''
                        UPDATE scores 
                        SET games_played = games_played + 1 
                        WHERE username = ?
                    ''', (username,))
                conn.commit()
            
            # Send leaderboard
            time.sleep(0.5)
            leaderboard = self.get_leaderboard()
            self.send_channel_message(leaderboard)
        else:
            self.send_channel_message(f"{COLOR}07,01Quiz ended! No points scored{RESET}")
        
        self.quiz_state = QuizState()

    def connect(self) -> bool:
        """Establish connection to the IRC server"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.irc = self.ssl_context.wrap_socket(sock)
            
            logging.info(f"Connecting to {self.server}:{self.port}...")
            self.irc.connect((self.server, self.port))
            
            self.send(f"NICK {self.nickname}")
            self.send(f"USER {self.nickname} 0 * :MansionNet Quiz Bot")
            
            buffer = ""
            while True:
                data = self.irc.recv(2048).decode("UTF-8")
                buffer += data
                
                if "PING" in buffer:
                    ping_token = buffer[buffer.find("PING"):].split()[1]
                    self.send(f"PONG {ping_token}")
                
                if "001" in buffer:  # RPL_WELCOME
                    for channel in self.channels:
                        self.send(f"JOIN {channel}")
                        time.sleep(1)
                    return True
                
                if "Closing Link" in buffer or "ERROR" in buffer:
                    return False
                    
        except Exception as e:
            logging.error(f"Connection error: {e}")
            return False

    def send(self, message: str):
        """Send a raw message to the IRC server"""
        try:
            if self.irc:
                self.irc.send(bytes(f"{message}\r\n", "UTF-8"))
                logging.debug(f"Sent: {message}")
            else:
                logging.error("IRC connection not established")
        except Exception as e:
            logging.error(f"Error sending message: {e}")

    def send_channel_message(self, message: str):
        """Send a formatted message to the current quiz channel"""
        if self.quiz_state.channel:
            # Format based on message type
            if "Question" in message:
                prefix = "◆"
            elif "Correct" in message:
                prefix = "✓"
            elif "Time's up" in message:
                prefix = "⏰"
            else:
                prefix = ""
            
            formatted = f"{prefix} {message}" if prefix else message
            self.send(f"PRIVMSG {self.quiz_state.channel} :{formatted}")
        else:
            logging.error("No channel set for message")

    def run(self):
        """Main bot loop with improved error handling"""
        while True:
            try:
                if self.connect():
                    buffer = ""
                    while True:
                        try:
                            buffer += self.irc.recv(2048).decode("UTF-8")
                            lines = buffer.split("\r\n")
                            buffer = lines.pop()
                            
                            for line in lines:
                                logging.debug(f"Processing line: {line}")
                                
                                if line.startswith("PING"):
                                    self.send(f"PONG {line.split()[1]}")
                                    continue
                                    
                                if "PRIVMSG" in line:
                                    parts = line.split("PRIVMSG", 1)[1].split(":", 1)
                                    if len(parts) != 2:
                                        continue
                                        
                                    channel = parts[0].strip()
                                    message = parts[1].strip()
                                    username = line[1:].split("!")[0]
                                    
                                    if channel in self.channels:
                                        self.handle_command(username, channel, message)
                                        
                        except UnicodeDecodeError:
                            buffer = ""
                            continue
                
                else:
                    logging.error("Failed to connect, retrying in 30 seconds...")
                    time.sleep(30)
                            
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(30)
                continue

if __name__ == "__main__":
    try:
        bot = QuizBot()
        bot.run()
    except Exception as e:
        logging.critical(f"Fatal error: {e}")