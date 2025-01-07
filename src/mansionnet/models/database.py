"""Database models and connection management."""
from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Generator, Optional, List, Dict, Any
import logging
import asyncio
from functools import partial

from ..config.settings import DB_CONFIG

logger = logging.getLogger(__name__)

class Database:
    """Database connection and schema management."""
    
    SCHEMA = {
        "scores": """
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
        """,
        "question_history": """
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
        """
    }

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection."""
        self.db_path = db_path or DB_CONFIG["path"]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_connections = set()
        self.operation_timeout = 10  # 10 second timeout for DB operations
        self.init_schema()

    async def _execute_with_timeout(self, operation, *args, **kwargs):
        """Execute a database operation with timeout."""
        try:
            async with asyncio.timeout(self.operation_timeout):
                return await asyncio.get_event_loop().run_in_executor(
                    None, operation, *args, **kwargs
                )
        except asyncio.TimeoutError:
            logger.error(f"Database operation timed out: {operation.__name__}")
            raise
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            raise

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create a database connection context."""
        conn = sqlite3.connect(self.db_path)
        self._active_connections.add(conn)
        try:
            yield conn
        finally:
            self._active_connections.remove(conn)
            conn.close()

    def init_schema(self) -> None:
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table_name, schema in self.SCHEMA.items():
                try:
                    cursor.execute(schema)
                except sqlite3.Error as e:
                    logger.error(f"Error creating table {table_name}: {e}")
            conn.commit()

    async def update_score(self, username: str, points: int, answer_time: float,
                          current_streak: int) -> None:
        """Update user score and statistics with timeout."""
        def _update():
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
                """, (
                    username, points, answer_time, current_streak, points,
                    points, answer_time, answer_time, current_streak,
                    current_streak, points, points
                ))
                conn.commit()

        try:
            await self._execute_with_timeout(_update)
        except Exception as e:
            logger.error(f"Failed to update score for {username}: {e}")

    async def get_leaderboard(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get the top players by score with timeout."""
        def _get_leaderboard():
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        username, total_score, correct_answers,
                        fastest_answer, longest_streak, highest_score
                    FROM scores
                    ORDER BY total_score DESC
                    LIMIT ?
                """, (limit,))
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

        try:
            return await self._execute_with_timeout(_get_leaderboard)
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            return []

    async def get_player_stats(self, username: str) -> Optional[Dict[str, Any]]:
        """Get detailed statistics for a player with timeout."""
        def _get_stats():
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        total_score, games_played, correct_answers,
                        fastest_answer, longest_streak, highest_score
                    FROM scores WHERE username = ?
                """, (username,))
                row = cursor.fetchone()
                if row:
                    return {
                        "total_score": row[0],
                        "games_played": row[1],
                        "correct_answers": row[2],
                        "fastest_answer": row[3],
                        "longest_streak": row[4],
                        "highest_score": row[5]
                    }
                return None

        try:
            return await self._execute_with_timeout(_get_stats)
        except Exception as e:
            logger.error(f"Failed to get stats for {username}: {e}")
            return None

    async def add_question_to_history(self, question: str, answer: str,
                                    category: str) -> None:
        """Add a new question to the history with timeout."""
        def _add_question():
            question_hash = f"{question}:{answer}"
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO question_history
                    (question_hash, question, answer, category, last_asked)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (question_hash, question, answer, category))
                conn.commit()

        try:
            await self._execute_with_timeout(_add_question)
        except Exception as e:
            logger.error(f"Failed to add question to history: {e}")

    async def update_question_stats(self, question_hash: str,
                                  answered_correctly: bool,
                                  answer_time: float) -> None:
        """Update statistics for a question with timeout."""
        def _update_stats():
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE question_history
                    SET times_asked = times_asked + 1,
                        times_answered_correctly = times_answered_correctly + ?,
                        average_answer_time = (
                            (average_answer_time * times_asked + ?) /
                            (times_asked + 1)
                        ),
                        last_asked = datetime('now')
                    WHERE question_hash = ?
                """, (int(answered_correctly), answer_time, question_hash))
                conn.commit()

        try:
            await self._execute_with_timeout(_update_stats)
        except Exception as e:
            logger.error(f"Failed to update question stats: {e}")

    async def close(self) -> None:
        """Close all active database connections with timeout."""
        logger.info("Closing database connections...")
        
        def _close_connections():
            for conn in self._active_connections.copy():
                try:
                    conn.close()
                    self._active_connections.remove(conn)
                except Exception as e:
                    logger.error(f"Error closing database connection: {e}")
        
        try:
            async with asyncio.timeout(5.0):  # 5 second timeout for cleanup
                await asyncio.get_event_loop().run_in_executor(None, _close_connections)
        except asyncio.TimeoutError:
            logger.error("Timeout while closing database connections")
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
            
        if self._active_connections:
            logger.warning(f"{len(self._active_connections)} database connections remain open")