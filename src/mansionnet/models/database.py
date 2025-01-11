"""Database models and connection management."""
import logging
import asyncio
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from contextlib import asynccontextmanager

from ..config.settings import DB_CONFIG

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass

class Database:
    """Database connection and schema management."""
    
    SCHEMA = {
        "question_history": """
            CREATE TABLE IF NOT EXISTS question_history (
                question_hash TEXT PRIMARY KEY,
                question TEXT,
                answer TEXT,
                category TEXT,
                subcategory TEXT,
                region TEXT,
                difficulty TEXT,
                times_asked INTEGER DEFAULT 1,
                times_answered_correctly INTEGER DEFAULT 0,
                last_asked TIMESTAMP,
                average_answer_time REAL DEFAULT 0,
                success_rate REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
        "scores": """
            CREATE TABLE IF NOT EXISTS scores (
                username TEXT PRIMARY KEY,
                total_score INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                fastest_answer REAL DEFAULT 999999,
                longest_streak INTEGER DEFAULT 0,
                highest_score INTEGER DEFAULT 0,
                last_played TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
    }

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database settings."""
        self.db_path = db_path or DB_CONFIG["path"]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection management
        self.pool = None
        self.pool_lock = asyncio.Lock()
        self._stopping = False
        self._active_connections: Set[aiosqlite.Connection] = set()
        
        # Configuration
        self.max_retries = DB_CONFIG.get("max_retries", 3)
        self.retry_delay = DB_CONFIG.get("retry_delay", 1)
        self.operation_timeout = DB_CONFIG.get("operation_timeout", 10)

    async def initialize(self) -> None:
        """Initialize database schema."""
        try:
            async with self.get_connection() as conn:
                for name, schema in self.SCHEMA.items():
                    try:
                        await conn.execute(schema)
                        await conn.commit()
                    except Exception as e:
                        raise DatabaseError(f"Error creating {name} table: {e}")
                        
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection with retry logic."""
        retry_count = 0
        conn = None
        
        while retry_count < self.max_retries:
            try:
                async with self.pool_lock:
                    if self._stopping:
                        raise DatabaseError("Database is shutting down")
                        
                    if not self.pool:
                        self.pool = await aiosqlite.connect(
                            self.db_path,
                            isolation_level=None  # Enable autocommit mode
                        )
                    conn = self.pool
                    
                self._active_connections.add(conn)
                yield conn
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count == self.max_retries:
                    raise DatabaseError(f"Failed to get database connection: {e}")
                await asyncio.sleep(self.retry_delay)
                
            finally:
                if conn:
                    self._active_connections.discard(conn)

    async def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        """Execute a SELECT query and return results."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute(query, params) as cursor:
                    return await cursor.fetchall()
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                logger.error(f"Query: {query}")
                logger.error(f"Params: {params}")
                raise DatabaseError(f"Query execution failed: {e}")

    async def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an UPDATE/INSERT/DELETE query and return affected rows."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute(query, params) as cursor:
                    await conn.commit()
                    return cursor.rowcount
            except Exception as e:
                logger.error(f"Update execution failed: {e}")
                logger.error(f"Query: {query}")
                logger.error(f"Params: {params}")
                raise DatabaseError(f"Update execution failed: {e}")

    async def add_question_to_history(
        self,
        question: str,
        answer: str,
        category: str,
        subcategory: str,
        region: str = "global",
        difficulty: str = "medium"
    ) -> None:
        """Add or update a question in history."""
        if not question or not answer:
            raise ValueError("Question and answer are required")
            
        question_hash = f"{question}:{answer}"
        query = """
            INSERT INTO question_history 
            (question_hash, question, answer, category, subcategory, 
             region, difficulty, last_asked)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(question_hash) DO UPDATE SET
                times_asked = times_asked + 1,
                last_asked = datetime('now')
        """
        params = (
            question_hash, question, answer, category,
            subcategory, region, difficulty
        )
        
        try:
            await self.execute_update(query, params)
        except Exception as e:
            logger.error(f"Failed to add/update question history: {e}")
            # Don't re-raise - allow the game to continue even if history fails

    async def update_question_stats(
        self,
        question: str,
        answer: str,
        was_correct: bool,
        answer_time: float
    ) -> None:
        """Update question statistics."""
        question_hash = f"{question}:{answer}"
        query = """
            UPDATE question_history
            SET times_asked = times_asked + 1,
                times_answered_correctly = times_answered_correctly + ?,
                average_answer_time = (average_answer_time * times_asked + ?) 
                                    / (times_asked + 1),
                success_rate = CAST(times_answered_correctly + ? AS FLOAT) 
                              / (times_asked + 1),
                last_asked = datetime('now')
            WHERE question_hash = ?
        """
        params = (int(was_correct), answer_time, int(was_correct), question_hash)
        
        try:
            await self.execute_update(query, params)
        except Exception as e:
            logger.error(f"Failed to update question stats: {e}")
            # Don't re-raise - allow the game to continue even if stats update fails

    async def get_player_stats(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a player's statistics."""
        query = """
            SELECT total_score, games_played, correct_answers,
                   fastest_answer, longest_streak, highest_score
            FROM scores 
            WHERE username = ?
        """
        
        results = await self.execute_query(query, (username,))
        if results:
            return {
                'total_score': results[0][0],
                'games_played': results[0][1],
                'correct_answers': results[0][2],
                'fastest_answer': results[0][3] if results[0][3] != 999999 else 0,
                'longest_streak': results[0][4],
                'highest_score': results[0][5]
            }
        return None

    async def update_score(
        self,
        username: str,
        points: int,
        answer_time: float,
        current_streak: int
    ) -> None:
        """Update a player's score and stats."""
        try:
            # Check if player exists
            existing_player = await self.get_player_stats(username)
            
            if not existing_player:
                # Insert new player record
                insert_query = """
                    INSERT INTO scores (
                        username, total_score, games_played, correct_answers,
                        fastest_answer, longest_streak, highest_score, last_played
                    )
                    VALUES (?, ?, 1, 1, ?, ?, ?, datetime('now'))
                """
                insert_params = (username, points, answer_time, current_streak, points)
                await self.execute_update(insert_query, insert_params)
            else:
                # Update existing player
                update_query = """
                    UPDATE scores SET
                        total_score = total_score + ?,
                        correct_answers = correct_answers + 1,
                        fastest_answer = MIN(CASE 
                            WHEN fastest_answer = 999999 THEN ? 
                            ELSE fastest_answer END, ?),
                        longest_streak = MAX(longest_streak, ?),
                        highest_score = MAX(highest_score, total_score + ?),
                        games_played = CASE 
                            WHEN last_played < datetime('now', '-1 hour') 
                            THEN games_played + 1 
                            ELSE games_played 
                        END,
                        last_played = datetime('now')
                    WHERE username = ?
                """
                update_params = (
                    points,           # total_score increment
                    answer_time,      # new fastest_answer (if no previous record)
                    answer_time,      # new fastest_answer (for MIN comparison)
                    current_streak,   # new longest_streak
                    points,           # for highest_score calculation
                    username          # identify the player
                )
                await self.execute_update(update_query, update_params)
                
        except Exception as e:
            logger.error(f"Error updating score for {username}: {e}")
            raise DatabaseError(f"Failed to update score: {e}")

    async def get_leaderboard(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top players by score."""
        query = """
            SELECT username, total_score, correct_answers,
                   fastest_answer, longest_streak
            FROM scores
            ORDER BY total_score DESC
            LIMIT ?
        """
        
        results = await self.execute_query(query, (limit,))
        return [{
            'username': row[0],
            'total_score': row[1],
            'correct_answers': row[2],
            'fastest_answer': row[3] if row[3] != 999999 else 0,
            'longest_streak': row[4]
        } for row in results]

    async def clean_old_questions(self, days: int = 7) -> int:
        """Remove old questions from history."""
        query = """
            DELETE FROM question_history
            WHERE last_asked < datetime('now', ?)
        """
        
        return await self.execute_update(query, (f'-{days} days',))

    async def close(self) -> None:
        """Close database connections."""
        self._stopping = True
        logger.info("Closing database connections...")
        
        try:
            async with asyncio.timeout(5.0):
                if self.pool:
                    await self.pool.close()
                    self.pool = None
                
                for conn in self._active_connections.copy():
                    try:
                        await conn.close()
                        self._active_connections.remove(conn)
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
        finally:
            self._active_connections.clear()  # Ensure set is empty
            self._stopping = False  # Reset stopping flag