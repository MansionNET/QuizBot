import logging
from typing import List, Dict, Optional
import asyncio
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, select, func, text

logger = logging.getLogger(__name__)

Base = declarative_base()

class Question(Base):
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    question_id = Column(String, unique=True, nullable=False)  # Unique ID from Mistral
    question_text = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    fun_fact = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Category of the question
    difficulty = Column(Integer, nullable=False)  # 1-3 for easy, medium, hard
    used = Column(Boolean, default=False)  # Track if question was used in a game
    last_used = Column(Float, nullable=True)  # Timestamp when question was last used

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True)
    nick = Column(String, unique=True, nullable=False)
    total_score = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    fastest_answer = Column(Float, nullable=True)  # Store fastest answer time in seconds

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None

    async def connect(self):
        """Connect to the database and create tables"""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False
            )
            
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
            logger.info("Database connection established")
            
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    async def disconnect(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")

    async def get_player_stats(self, nick: str) -> Optional[Dict]:
        """Get stats for a specific player"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Player).where(Player.nick == nick)
            )
            player = result.scalar_one_or_none()
            
            if player:
                return {
                    'total_score': player.total_score,
                    'correct_answers': player.correct_answers,
                    'best_streak': player.best_streak,
                    'fastest_answer': player.fastest_answer
                }
            return None

    async def update_player_stats(
        self,
        nick: str,
        score: int,
        correct_answers: int,
        best_streak: int,
        answer_time: Optional[float] = None
    ):
        """Update or create player stats"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Player).where(Player.nick == nick)
            )
            player = result.scalar_one_or_none()
            
            if player:
                player.total_score += score
                player.correct_answers += correct_answers
                player.best_streak = max(player.best_streak, best_streak)
                if answer_time is not None:
                    if player.fastest_answer is None or answer_time < player.fastest_answer:
                        player.fastest_answer = answer_time
            else:
                player = Player(
                    nick=nick,
                    total_score=score,
                    correct_answers=correct_answers,
                    best_streak=best_streak,
                    fastest_answer=answer_time
                )
                session.add(player)
                
            await session.commit()

    async def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get top players by total score"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Player)
                .order_by(Player.total_score.desc())
                .limit(limit)
            )
            players = result.scalars().all()
            
            return [
                {
                    'nick': player.nick,
                    'total_score': player.total_score,
                    'correct_answers': player.correct_answers,
                    'best_streak': player.best_streak,
                    'fastest_answer': player.fastest_answer
                }
                for player in players
            ]
            
    async def add_questions(self, questions: List[Dict]) -> int:
        """Add multiple questions to the database. Returns number of questions added."""
        async with self.SessionLocal() as session:
            added = 0
            for q in questions:
                # Check for duplicate or very similar questions
                similar = await session.execute(
                    select(Question).where(
                        (Question.answer == q['answer']) |
                        (Question.question_text.like(f"%{q['answer']}%"))
                    )
                )
                if not similar.scalar_one_or_none():
                    question = Question(
                        question_id=q['id'],
                        question_text=q['question'],
                        answer=q['answer'],
                        fun_fact=q['fun_fact'],
                        category=q.get('category', 'general'),
                        difficulty=q.get('difficulty', 2),  # Default to medium
                        used=False
                    )
                    session.add(question)
                    added += 1
            await session.commit()
            return added
            
    async def get_unused_question(self) -> Optional[Dict]:
        """Get a random unused question and mark it as used."""
        async with self.SessionLocal() as session:
            # Get random unused question, prioritizing questions that haven't been used recently
            result = await session.execute(
                select(Question)
                .where(Question.used == False)
                .order_by(
                    Question.last_used.nulls_first(),
                    func.random()
                )
                .limit(1)
            )
            question = result.scalar_one_or_none()
            
            if question:
                # Mark as used and update timestamp
                question.used = True
                question.last_used = func.time()
                await session.commit()
                
                return {
                    'id': question.question_id,
                    'question': question.question_text,
                    'answer': question.answer,
                    'fun_fact': question.fun_fact,
                    'category': question.category,
                    'difficulty': question.difficulty
                }
            return None
            
    async def reset_used_questions(self):
        """Reset all questions to unused state."""
        async with self.SessionLocal() as session:
            await session.execute(
                text("UPDATE questions SET used = FALSE")
            )
            await session.commit()
            
    async def count_questions(self, unused_only: bool = False) -> int:
        """Count total or unused questions in database."""
        async with self.SessionLocal() as session:
            query = select(func.count(Question.id))
            if unused_only:
                query = query.where(Question.used == False)
            result = await session.execute(query)
            return result.scalar_one()
