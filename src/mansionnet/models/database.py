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
                difficulty TEXT,
                times_asked INTEGER DEFAULT 1,
                times_answered_correctly INTEGER DEFAULT 0,
                last_asked TIMESTAMP,
                average_answer_time REAL DEFAULT 0,
                success_rate REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "answer_tracking": """
            CREATE TABLE IF NOT EXISTS answer_tracking (
                answer TEXT PRIMARY KEY,
                category TEXT,
                times_used INTEGER DEFAULT 1,
                success_rate REAL DEFAULT 0,
                average_answer_time REAL DEFAULT 0,
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
                success_rate REAL DEFAULT 0,
                average_answer_time REAL DEFAULT 0,
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
        region: str = "global",
        difficulty: str = "medium"
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
                    (question_hash, question, answer, category, subcategory, region, difficulty, last_asked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (question_hash, question, answer, category, subcategory, region, difficulty)))
                
                # Update answer tracking
                await self.execute_with_timeout(conn.execute("""
                    INSERT INTO answer_tracking (answer, category, last_used)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(answer) DO UPDATE SET
                        times_used = times_used + 1,
                        success_rate = (success_rate * times_used) / (times_used + 1),
                        last_used = datetime('now')
                """, (answer.lower(), category)))
                
                # Update category tracking
                await self.execute_with_timeout(conn.execute("""
                    INSERT INTO category_tracking (category, subcategory, region, last_used)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(category, subcategory, region) DO UPDATE SET
                        times_used = times_used + 1,
                        success_rate = (success_rate * times_used) / (times_used + 1),
                        last_used = datetime('now')
                """, (category, subcategory, region)))
                
                await conn.commit()
                
            except Exception as e:
                logger.error(f"Failed to add question to history: {e}")
                raise DatabaseError(f"Failed to add question: {e}")

    async def get_recently_used_answers(self, days: int = 15) -> List[Dict[str, Any]]:
        """Get answers that have been used recently with their metadata."""
        async with self.get_connection() as conn:
            try:
                # Get both answers and their categories with usage stats
                async with conn.execute("""
                    SELECT 
                        a.answer,
                        a.category,
                        a.times_used as usage_count,
                        a.last_used,
                        GROUP_CONCAT(DISTINCT q.question) as questions
                    FROM answer_tracking a
                    LEFT JOIN question_history q ON q.answer = a.answer
                    WHERE a.last_used > datetime('now', ?)
                    GROUP BY a.answer, a.category
                    ORDER BY last_used DESC, usage_count DESC
                """, (f'-{days} days',)) as cursor:
                    rows = await cursor.fetchall()
                    
                    # Return detailed answer history
                    return [{
                        'answer': row[0],
                        'category': row[1],
                        'usage_count': row[2],
                        'last_used': row[3],
                        'questions': row[4].split(',') if row[4] else []
                    } for row in rows]
            except Exception as e:
                logger.error(f"Failed to get recent answers: {e}")
                return []

    async def get_category_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed statistics for categories including performance metrics."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT 
                        c.category,
                        c.subcategory,
                        c.region,
                        c.times_used,
                        c.success_rate,
                        c.average_answer_time,
                        COUNT(DISTINCT q.question_hash) as unique_questions,
                        AVG(q.success_rate) as avg_question_success,
                        AVG(q.average_answer_time) as avg_question_time,
                        MAX(c.last_used) as last_used
                    FROM category_tracking c
                    LEFT JOIN question_history q 
                        ON q.category = c.category 
                        AND q.subcategory = c.subcategory
                        AND q.region = c.region
                    GROUP BY c.category, c.subcategory, c.region
                    ORDER BY c.times_used DESC
                """) as cursor:
                    rows = await cursor.fetchall()
                    stats = {}
                    
                    for row in rows:
                        cat = row[0]
                        subcat = row[1]
                        region = row[2]
                        
                        if cat not in stats:
                            stats[cat] = {
                                'total_uses': 0,
                                'success_rate': 0,
                                'avg_answer_time': 0,
                                'subcategories': {},
                                'regions': {},
                                'performance': {
                                    'unique_questions': 0,
                                    'avg_success_rate': 0,
                                    'avg_answer_time': 0
                                }
                            }
                        
                        # Update category totals
                        stats[cat]['total_uses'] += row[3]  # times_used
                        stats[cat]['success_rate'] = (
                            stats[cat]['success_rate'] + row[4]
                        ) / 2 if stats[cat]['success_rate'] else row[4]
                        stats[cat]['avg_answer_time'] = (
                            stats[cat]['avg_answer_time'] + row[5]
                        ) / 2 if stats[cat]['avg_answer_time'] else row[5]
                        
                        # Track subcategory stats
                        if subcat:
                            stats[cat]['subcategories'][subcat] = {
                                'times_used': row[3],
                                'success_rate': row[4],
                                'avg_answer_time': row[5],
                                'unique_questions': row[6],
                                'last_used': row[9]
                            }
                        
                        # Track region stats
                        if region:
                            stats[cat]['regions'][region] = {
                                'times_used': row[3],
                                'success_rate': row[4],
                                'avg_answer_time': row[5],
                                'unique_questions': row[6],
                                'last_used': row[9]
                            }
                        
                        # Update performance metrics
                        stats[cat]['performance']['unique_questions'] += row[6]
                        stats[cat]['performance']['avg_success_rate'] = (
                            stats[cat]['performance']['avg_success_rate'] + row[7]
                        ) / 2 if stats[cat]['performance']['avg_success_rate'] else row[7]
                        stats[cat]['performance']['avg_answer_time'] = (
                            stats[cat]['performance']['avg_answer_time'] + row[8]
                        ) / 2 if stats[cat]['performance']['avg_answer_time'] else row[8]
                    
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
                # Get current question info
                async with conn.execute("""
                    SELECT answer, category, subcategory, region, times_asked
                    FROM question_history
                    WHERE question_hash = ?
                """, (question_hash,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        raise DatabaseError(f"Question not found: {question_hash}")
                    
                    answer, category, subcategory, region, times_asked = row
                    new_times_asked = times_asked + 1
                
                # Update question history with success rate
                await self.execute_with_timeout(conn.execute("""
                    UPDATE question_history
                    SET times_asked = times_asked + 1,
                        times_answered_correctly = times_answered_correctly + ?,
                        average_answer_time = (
                            (average_answer_time * times_asked + ?) /
                            (times_asked + 1)
                        ),
                        success_rate = CAST(times_answered_correctly + ? AS FLOAT) / (times_asked + 1),
                        last_asked = datetime('now')
                    WHERE question_hash = ?
                """, (int(answered_correctly), answer_time, int(answered_correctly), question_hash)))
                
                # Update answer tracking
                await self.execute_with_timeout(conn.execute("""
                    UPDATE answer_tracking
                    SET success_rate = (
                            (success_rate * times_used + ?) / (times_used + 1)
                        ),
                        average_answer_time = (
                            (average_answer_time * times_used + ?) / (times_used + 1)
                        )
                    WHERE answer = ?
                """, (int(answered_correctly), answer_time, answer.lower())))
                
                # Update category tracking
                await self.execute_with_timeout(conn.execute("""
                    UPDATE category_tracking
                    SET success_rate = (
                            (success_rate * times_used + ?) / (times_used + 1)
                        ),
                        average_answer_time = (
                            (average_answer_time * times_used + ?) / (times_used + 1)
                        )
                    WHERE category = ? AND subcategory = ? AND region = ?
                """, (int(answered_correctly), answer_time, category, subcategory, region)))
                
                await conn.commit()
                
            except Exception as e:
                logger.error(f"Failed to update question stats: {e}")
                raise DatabaseError(f"Failed to update question stats: {e}")

    async def get_question_performance_metrics(self, category: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed performance metrics for questions, optionally filtered by category."""
        async with self.get_connection() as conn:
            try:
                query = """
                    SELECT 
                        difficulty,
                        COUNT(*) as total_questions,
                        AVG(success_rate) as avg_success_rate,
                        AVG(average_answer_time) as avg_answer_time,
                        SUM(CASE WHEN success_rate < 0.3 THEN 1 ELSE 0 END) as hard_questions,
                        SUM(CASE WHEN success_rate > 0.7 THEN 1 ELSE 0 END) as easy_questions
                    FROM question_history
                    WHERE times_asked >= 5
                """
                params = []
                if category:
                    query += " AND category = ?"
                    params.append(category)
                
                query += " GROUP BY difficulty ORDER BY difficulty"
                
                async with conn.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    
                    metrics = {
                        'difficulty_distribution': {},
                        'overall': {
                            'total_questions': 0,
                            'avg_success_rate': 0,
                            'avg_answer_time': 0,
                            'hard_questions': 0,
                            'easy_questions': 0
                        }
                    }
                    
                    for row in rows:
                        diff = row[0] or 'medium'  # Default to medium if None
                        metrics['difficulty_distribution'][diff] = {
                            'total_questions': row[1],
                            'avg_success_rate': row[2],
                            'avg_answer_time': row[3],
                            'hard_questions': row[4],
                            'easy_questions': row[5]
                        }
                        
                        # Update overall metrics
                        metrics['overall']['total_questions'] += row[1]
                        metrics['overall']['hard_questions'] += row[4]
                        metrics['overall']['easy_questions'] += row[5]
                    
                    # Calculate overall averages if we have data
                    if metrics['overall']['total_questions'] > 0:
                        total = metrics['overall']['total_questions']
                        metrics['overall']['avg_success_rate'] = sum(
                            d['avg_success_rate'] * d['total_questions']
                            for d in metrics['difficulty_distribution'].values()
                        ) / total
                        metrics['overall']['avg_answer_time'] = sum(
                            d['avg_answer_time'] * d['total_questions']
                            for d in metrics['difficulty_distribution'].values()
                        ) / total
                    
                    return metrics
                    
            except Exception as e:
                logger.error(f"Failed to get question performance metrics: {e}")
                return {}

    async def get_question_suggestions(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get suggestions for questions that might need adjustment based on performance."""
        async with self.get_connection() as conn:
            try:
                async with conn.execute("""
                    SELECT 
                        question,
                        answer,
                        category,
                        difficulty,
                        times_asked,
                        success_rate,
                        average_answer_time
                    FROM question_history
                    WHERE times_asked >= 5
                    AND (
                        (difficulty = 'easy' AND success_rate < 0.3)
                        OR (difficulty = 'hard' AND success_rate > 0.7)
                        OR (success_rate < 0.2)
                        OR (success_rate > 0.8)
                        OR (average_answer_time > 15)
                    )
                    ORDER BY times_asked DESC
                    LIMIT ?
                """, (count,)) as cursor:
                    rows = await cursor.fetchall()
                    return [{
                        'question': row[0],
                        'answer': row[1],
                        'category': row[2],
                        'difficulty': row[3],
                        'times_asked': row[4],
                        'success_rate': row[5],
                        'average_answer_time': row[6],
                        'suggestion': self._get_question_suggestion(row[3], row[5], row[6])
                    } for row in rows]
            except Exception as e:
                logger.error(f"Failed to get question suggestions: {e}")
                return []

    def _get_question_suggestion(
        self,
        difficulty: str,
        success_rate: float,
        answer_time: float
    ) -> str:
        """Generate a suggestion for question adjustment based on metrics."""
        suggestions = []
        
        if difficulty == 'easy' and success_rate < 0.3:
            suggestions.append("Consider increasing difficulty to 'medium'")
        elif difficulty == 'hard' and success_rate > 0.7:
            suggestions.append("Consider decreasing difficulty to 'medium'")
            
        if success_rate < 0.2:
            suggestions.append("Question may be too difficult or unclear")
        elif success_rate > 0.8:
            suggestions.append("Question may be too easy")
            
        if answer_time > 15:
            suggestions.append("Question may take too long to answer")
            
        return "; ".join(suggestions) if suggestions else "No adjustment needed"

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
