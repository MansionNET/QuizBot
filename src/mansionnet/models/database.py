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
    """Database connection and schema management with connection pooling."""
    
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
                last_played TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "question_history": """
            CREATE TABLE IF NOT EXISTS question_history (
                question_hash TEXT PRIMARY KEY,
                question TEXT,
                answer TEXT,
                category TEXT,
                subcategory TEXT,
                region TEXT,
                times_asked INTEGER DEFAULT 1,
                times_answered_correctly INTEGER DEFAULT 0,
                last_asked TIMESTAMP,
                average_answer_time REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "answer_tracking": """
            CREATE TABLE IF NOT EXISTS answer_tracking (
                answer TEXT PRIMARY KEY,
                category TEXT,
                times_used INTEGER DEFAULT 1,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "category_tracking": """
            CREATE TABLE IF NOT EXISTS category_tracking (
                category TEXT,
                subcategory TEXT,
                region TEXT,
                times_used INTEGER DEFAULT 1,
                last_used TIMESTAMP,
                PRIMARY KEY (category, subcategory, region)
            )
        """
    }

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database with connection pool settings."""
        self.db_path = db_path or DB_CONFIG["path"]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection pool settings
        self.pool = None
        self.pool_lock = asyncio.Lock()
        self.max_connections = DB_CONFIG.get("max_connections", 10)
        self.min_connections = DB_CONFIG.get("min_connections", 1)
        self.max_retries = DB_CONFIG.get("max_retries", 3)
        self.retry_delay = DB_CONFIG.get("retry_delay", 1)
        self.operation_timeout = DB_CONFIG.get("operation_timeout", 10)
        
        # Track active connections
        self._active_connections: Set[aiosqlite.Connection] = set()
        self._stopping = False

    async def initialize(self) -> None:
        """Initialize the database schema and connection pool."""
        try:
            async with self.get_connection() as conn:
                # Drop existing tables to ensure clean schema
                drop_tables = [
                    "DROP TABLE IF EXISTS question_history",
                    "DROP TABLE IF EXISTS answer_tracking",
                    "DROP TABLE IF EXISTS category_tracking"
                ]
                for drop_sql in drop_tables:
                    await conn.execute(drop_sql)
                    await conn.commit()
                
                # Create tables with new schema
                for table_name, schema in self.SCHEMA.items():
                    try:
                        await conn.execute(schema)
                        await conn.commit()
                    except Exception as e:
                        raise DatabaseError(f"Error creating table {table_name}: {e}")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @asynccontextmanager
    async def get_connection(self):
        """
        Get a database connection from the pool.
        Implements retry logic and connection pooling.
        """
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
                            isolation_level=None,  # Enable autocommit mode
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

    async def execute_with_timeout(self, operation):
        """Execute a database operation with timeout."""
        try:
            async with asyncio.timeout(self.operation_timeout):
                return await operation
        except asyncio.TimeoutError:
            raise DatabaseError(f"Operation timed out after {self.operation_timeout} seconds")
        except Exception as e:
            raise DatabaseError(f"Database operation failed: {e}")

    async def update_score(
        self,
        username: str,
        points: int,
        answer_time: float,
        current_streak: int
    ) -> None:
        """Update user score and statistics."""
        if not username or points < 0 or answer_time < 0:
            raise ValueError("Invalid score update parameters")
            
        async with self.get_connection() as conn:
            try:
                await self.execute_with_timeout(conn.execute("""
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
                )))
                await conn.commit()
                
            except Exception as e:
                logger.error(f"Failed to update score for {username}: {e}")
                raise DatabaseError(f"Score update failed: {e}")

    async def get_leaderboard(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get the top players by score."""
        if limit < 1:
            raise ValueError("Leaderboard limit must be positive")
            
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT
                        username, total_score, correct_answers,
                        fastest_answer, longest_streak, highest_score
                    FROM scores
                    ORDER BY total_score DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
                    
            except Exception as e:
                logger.error(f"Failed to get leaderboard: {e}")
                return []

    async def get_player_stats(self, username: str) -> Optional[Dict[str, Any]]:
        """Get detailed statistics for a player."""
        if not username:
            raise ValueError("Username cannot be empty")
            
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT
                        total_score, games_played, correct_answers,
                        fastest_answer, longest_streak, highest_score
                    FROM scores WHERE username = ?
                """, (username,)) as cursor:
                    row = await cursor.fetchone()
                    
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
                    
            except Exception as e:
                logger.error(f"Failed to get stats for {username}: {e}")
                return None

    async def add_question_to_history(
        self,
        question: str,
        answer: str,
        category: str,
        subcategory: str,
        region: str = "global"
    ) -> None:
        """Add a new question to the history and update tracking tables."""
        if not question or not answer:
            raise ValueError("Question and answer are required")
            
        question_hash = f"{question}:{answer}"
        async with self.get_connection() as conn:
            try:
                # Add to question history
                await self.execute_with_timeout(conn.execute("""
                    INSERT INTO question_history
                    (question_hash, question, answer, category, subcategory, region, last_asked)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (question_hash, question, answer, category, subcategory, region)))
                
                # Update answer tracking
                await self.execute_with_timeout(conn.execute("""
                    INSERT INTO answer_tracking (answer, category, last_used)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(answer) DO UPDATE SET
                        times_used = times_used + 1,
                        last_used = datetime('now')
                """, (answer.lower(), category)))
                
                # Update category tracking
                await self.execute_with_timeout(conn.execute("""
                    INSERT INTO category_tracking (category, subcategory, region, last_used)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(category, subcategory, region) DO UPDATE SET
                        times_used = times_used + 1,
                        last_used = datetime('now')
                """, (category, subcategory, region)))
                
                await conn.commit()
                
            except Exception as e:
                logger.error(f"Failed to add question to history: {e}")
                raise DatabaseError(f"Failed to add question: {e}")

    async def get_recently_used_answers(self, days: int = 15) -> List[str]:
        """Get answers that have been used recently."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT answer FROM answer_tracking
                    WHERE last_used > datetime('now', ?)
                """, (f'-{days} days',)) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
            except Exception as e:
                logger.error(f"Failed to get recent answers: {e}")
                return []

    async def get_category_stats(self) -> Dict[str, Dict[str, int]]:
        """Get usage statistics for categories and subcategories."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT category, subcategory, region, times_used
                    FROM category_tracking
                    ORDER BY times_used DESC
                """) as cursor:
                    rows = await cursor.fetchall()
                    stats = {}
                    for row in rows:
                        cat = row[0]
                        subcat = row[1]
                        region = row[2]
                        times = row[3]
                        
                        if cat not in stats:
                            stats[cat] = {'total': 0, 'subcategories': {}, 'regions': {}}
                        
                        stats[cat]['total'] += times
                        if subcat:
                            stats[cat]['subcategories'][subcat] = \
                                stats[cat]['subcategories'].get(subcat, 0) + times
                        if region:
                            stats[cat]['regions'][region] = \
                                stats[cat]['regions'].get(region, 0) + times
                    
                    return stats
            except Exception as e:
                logger.error(f"Failed to get category stats: {e}")
                return {}

    async def get_least_used_categories(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get categories and subcategories that have been used least recently."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT category, subcategory, region, times_used, last_used
                    FROM category_tracking
                    ORDER BY times_used ASC, last_used ASC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return [{
                        'category': row[0],
                        'subcategory': row[1],
                        'region': row[2],
                        'times_used': row[3],
                        'last_used': row[4]
                    } for row in rows]
            except Exception as e:
                logger.error(f"Failed to get least used categories: {e}")
                return []

    async def update_question_stats(
        self,
        question_hash: str,
        answered_correctly: bool,
        answer_time: float
    ) -> None:
        """Update statistics for a question."""
        if not question_hash or answer_time < 0:
            raise ValueError("Invalid question stats parameters")
            
        async with self.get_connection() as conn:
            try:
                await self.execute_with_timeout(conn.execute("""
                    UPDATE question_history
                    SET times_asked = times_asked + 1,
                        times_answered_correctly = times_answered_correctly + ?,
                        average_answer_time = (
                            (average_answer_time * times_asked + ?) /
                            (times_asked + 1)
                        ),
                        last_asked = datetime('now')
                    WHERE question_hash = ?
                """, (int(answered_correctly), answer_time, question_hash)))
                await conn.commit()
                
            except Exception as e:
                logger.error(f"Failed to update question stats: {e}")
                raise DatabaseError(f"Failed to update question stats: {e}")

    async def cleanup_old_questions(self, days: int = 30) -> int:
        """Remove questions that haven't been asked in specified days."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    DELETE FROM question_history
                    WHERE last_asked < datetime('now', ?)
                """, (f'-{days} days',)) as cursor:
                    await conn.commit()
                    return cursor.rowcount
                    
            except Exception as e:
                logger.error(f"Failed to cleanup old questions: {e}")
                return 0

    async def close(self) -> None:
        """Close all database connections."""
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
                        logger.error(f"Error closing database connection: {e}")
                        
        except asyncio.TimeoutError:
            logger.error("Database cleanup timed out")
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
        finally:
            if self._active_connections:
                logger.warning(
                    f"{len(self._active_connections)} database connections "
                    "remain open"
                )
