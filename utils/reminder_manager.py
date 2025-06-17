"""
Advanced reminder management system with SQLite backend
Provides high-performance, concurrent-safe reminder operations
"""

import asyncio
import aiosqlite
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set
import pytz
from dataclasses import dataclass
from contextlib import asynccontextmanager
from .background_task_manager import background_task_manager, io_bound, TaskPriority
from .time_parser import time_parser
from .timezone_manager import timezone_manager, DEFAULT_TIMEZONE as SHARED_DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

# Constants
MAX_REMINDERS_PER_USER = 25
MIN_REMINDER_INTERVAL = 60  # Minimum 60 seconds between reminders
# DEFAULT_TIMEZONE now imported from shared timezone_manager
DB_PATH = "./data/reminders.db"
CACHE_TTL = 300  # 5 minutes cache TTL


@dataclass
class Reminder:
    """Reminder data structure"""
    timestamp: float
    user_id: int
    message: str
    timezone: str
    created_at: float


@dataclass
class CacheEntry:
    """Cache entry with TTL"""
    data: any
    expires_at: float


class ReminderManagerV2:
    """Advanced reminder management with SQLite backend and caching"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.db_path = DB_PATH
            self.dm_failed_users = set()  # Track users with failed DMs
            
            # Cache layer
            self._cache: Dict[str, CacheEntry] = {}
            self._cache_lock = asyncio.Lock()
            
            # Event-driven architecture
            self._reminder_added_event = asyncio.Event()
            self._next_reminder_time = None
            
            # Connection pool
            self._connection_pool: List[aiosqlite.Connection] = []
            self._pool_lock = asyncio.Lock()
            self._max_connections = 5
            
            # Ensure data directory exists
            os.makedirs("./data", exist_ok=True)
            
            logger.info(f"Initializing ReminderManagerV2 instance {id(self)}")
    
    async def initialize(self):
        """Initialize the database and connection pool"""
        await self._init_database()
        await self._init_connection_pool()
        
        # Start background task manager
        await background_task_manager.start()
        
        # Migrate from old JSON-based system if needed
        await self._migrate_from_json()
        
        # Add channel_id column if it doesn't exist
        await self._add_channel_id_column()
    
    async def _init_database(self):
        """Initialize SQLite database with proper schema"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    channel_id INTEGER,
                    UNIQUE(timestamp, user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_timezones (
                    user_id INTEGER PRIMARY KEY,
                    timezone TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            
            # Create indexes for performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_timestamp ON reminders(timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id)")
            # Note: Partial indexes with parameters are not supported in SQLite
            
            await db.commit()
            logger.info("Database schema initialized")
    
    async def _init_connection_pool(self):
        """Initialize connection pool for better concurrency"""
        async with self._pool_lock:
            for _ in range(self._max_connections):
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                self._connection_pool.append(conn)
            logger.info(f"Initialized connection pool with {self._max_connections} connections")
    
    @asynccontextmanager
    async def _get_connection(self):
        """Get a connection from the pool"""
        async with self._pool_lock:
            if self._connection_pool:
                conn = self._connection_pool.pop()
            else:
                # Create temporary connection if pool is exhausted
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                logger.warning("Connection pool exhausted, creating temporary connection")
        
        try:
            yield conn
        finally:
            async with self._pool_lock:
                if len(self._connection_pool) < self._max_connections:
                    self._connection_pool.append(conn)
                else:
                    await conn.close()
    
    async def _migrate_from_json(self):
        """Migrate data from old JSON-based system"""
        old_reminders_file = "./data/reminders.json"
        old_timezones_file = "./data/user_timezones.json"
        
        # Check if we need to migrate
        async with self._get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM reminders")
            reminder_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM user_timezones")
            timezone_count = (await cursor.fetchone())[0]
        
        if reminder_count > 0 or timezone_count > 0:
            logger.info("Database already contains data, skipping migration")
            return
        
        # Migrate reminders
        if os.path.exists(old_reminders_file):
            try:
                with open(old_reminders_file, 'r') as f:
                    data = json.load(f)
                
                async with self._get_connection() as db:
                    for ts, (uid, msg, tz) in data.items():
                        await db.execute("""
                            INSERT OR IGNORE INTO reminders (timestamp, user_id, message, timezone, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (float(ts), int(uid), msg, tz, time.time()))
                    await db.commit()
                
                logger.info(f"Migrated {len(data)} reminders from JSON to SQLite")
                
                # Backup and remove old file
                os.rename(old_reminders_file, f"{old_reminders_file}.backup")
                
            except Exception as e:
                logger.error(f"Failed to migrate reminders: {e}")
        
        # Migrate timezones
        if os.path.exists(old_timezones_file):
            try:
                with open(old_timezones_file, 'r') as f:
                    data = json.load(f)
                
                async with self._get_connection() as db:
                    for uid, tz in data.items():
                        await db.execute("""
                            INSERT OR REPLACE INTO user_timezones (user_id, timezone, updated_at)
                            VALUES (?, ?, ?)
                        """, (int(uid), tz, time.time()))
                    await db.commit()
                
                logger.info(f"Migrated {len(data)} user timezones from JSON to SQLite")
                
                # Backup and remove old file
                os.rename(old_timezones_file, f"{old_timezones_file}.backup")
                
            except Exception as e:
                logger.error(f"Failed to migrate timezones: {e}")
    
    async def _add_channel_id_column(self):
        """Add channel_id column to existing reminders table if it doesn't exist"""
        try:
            async with self._get_connection() as db:
                # Check if column exists
                cursor = await db.execute("PRAGMA table_info(reminders)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                if 'channel_id' not in column_names:
                    logger.info("Adding channel_id column to reminders table")
                    await db.execute("ALTER TABLE reminders ADD COLUMN channel_id INTEGER")
                    await db.commit()
                    logger.info("Successfully added channel_id column")
        except Exception as e:
            logger.error(f"Failed to add channel_id column: {e}")
    
    async def _get_cache(self, key: str) -> Optional[any]:
        """Get item from cache if not expired"""
        async with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() < entry.expires_at:
                    return entry.data
                else:
                    # Remove expired entry
                    del self._cache[key]
            return None
    
    async def _set_cache(self, key: str, data: any, ttl: int = CACHE_TTL):
        """Set item in cache with TTL"""
        async with self._cache_lock:
            self._cache[key] = CacheEntry(
                data=data,
                expires_at=time.time() + ttl
            )
    
    async def _invalidate_cache(self, pattern: str = None):
        """Invalidate cache entries matching pattern"""
        async with self._cache_lock:
            if pattern is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self._cache[key]
    
    async def add_reminder(self, user_id: int, reminder_text: str, trigger_time: float, timezone: str, channel_id: int = None) -> Tuple[bool, str]:
        """Add a new reminder with optional channel context"""
        async with self._lock:
            # Check if time is in the past
            if trigger_time <= time.time():
                return False, "Cannot set reminders for the past"
            
            # Check user's reminder count
            async with self._get_connection() as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM reminders WHERE user_id = ?",
                    (user_id,)
                )
                count = (await cursor.fetchone())[0]
                
                if count >= MAX_REMINDERS_PER_USER:
                    return False, f"You already have {MAX_REMINDERS_PER_USER} reminders set"
                
                # Add the reminder using background task for better performance
                try:
                    # Signal that a reminder was added immediately for event-driven processing
                    self._reminder_added_event.set()
                    
                    success = await background_task_manager.submit_function(
                        self._background_save_reminder,
                        user_id, reminder_text, trigger_time, timezone, channel_id,
                        task_id=f"save_reminder_{user_id}_{int(trigger_time)}",
                        priority=TaskPriority.HIGH
                    )
                    
                    if success:
                        return True, "Reminder set successfully"
                    else:
                        return False, "Failed to queue reminder for saving"
                    
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        return False, "You already have a reminder at this exact time"
                    logger.error(f"Failed to add reminder: {e}")
                    return False, "Failed to add reminder"
    
    async def get_user_reminders(self, user_id: int) -> List[Tuple[float, str, str, Optional[int]]]:
        """Get all reminders for a user sorted by time with channel info"""
        # Check cache first
        cache_key = f"user_reminders_{user_id}"
        cached_result = await self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timestamp, message, timezone, channel_id
                FROM reminders
                WHERE user_id = ?
                ORDER BY timestamp ASC
            """, (user_id,))
            
            reminders = [(row['timestamp'], row['message'], row['timezone'], row['channel_id']) 
                        for row in await cursor.fetchall()]
            
            # Cache the result
            await self._set_cache(cache_key, reminders)
            
            return reminders
    
    async def cancel_reminder(self, user_id: int, timestamp: float) -> Tuple[bool, str]:
        """Cancel a specific reminder"""
        async with self._lock:
            async with self._get_connection() as db:
                cursor = await db.execute("""
                    SELECT message FROM reminders 
                    WHERE timestamp = ? AND user_id = ?
                """, (timestamp, user_id))
                
                row = await cursor.fetchone()
                if not row:
                    return False, "Reminder not found"
                
                message = row['message']
                
                # Use background task for deletion
                success = await background_task_manager.submit_function(
                    self._background_delete_reminder,
                    timestamp, user_id,
                    task_id=f"delete_reminder_{user_id}_{int(timestamp)}",
                    priority=TaskPriority.HIGH
                )
                
                if success:
                    return True, f"Cancelled reminder: {message}"
                else:
                    return False, "Failed to queue reminder for deletion"
    
    async def get_due_reminders(self) -> List[Tuple[float, int, str, str, Optional[int]]]:
        """Get all reminders that are due (past current time) with channel info"""
        current_time = time.time()
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timestamp, user_id, message, timezone, channel_id
                FROM reminders
                WHERE timestamp <= ?
                ORDER BY timestamp ASC
            """, (current_time,))
            
            return [(row['timestamp'], row['user_id'], row['message'], row['timezone'], row['channel_id'])
                   for row in await cursor.fetchall()]
    
    async def get_next_reminder_time(self) -> Optional[float]:
        """Get the timestamp of the next upcoming reminder"""
        # Check cache first
        cached_result = await self._get_cache("next_reminder")
        if cached_result is not None:
            return cached_result
        
        current_time = time.time()
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT MIN(timestamp) as next_time
                FROM reminders
                WHERE timestamp > ?
            """, (current_time,))
            
            row = await cursor.fetchone()
            next_time = row['next_time'] if row and row['next_time'] else None
            
            # Cache for a shorter period since this changes frequently
            await self._set_cache("next_reminder", next_time, ttl=60)
            
            return next_time
    
    async def mark_reminder_sent(self, timestamp: float):
        """Remove a reminder after it has been sent"""
        async with self._lock:
            # Use background task for deletion
            await background_task_manager.submit_function(
                self._background_delete_reminder,
                timestamp,
                task_id=f"mark_sent_{int(timestamp)}",
                priority=TaskPriority.NORMAL
            )
    
    async def set_user_timezone(self, user_id: int, timezone: str) -> Tuple[bool, str]:
        """Set a user's timezone preference - delegates to shared timezone manager"""
        return await timezone_manager.set_user_timezone(user_id, timezone)
    
    async def get_user_timezone(self, user_id: int) -> str:
        """Get a user's timezone or return default - delegates to shared timezone manager"""
        return await timezone_manager.get_user_timezone(user_id)
    
    def parse_natural_time(self, time_str: str, user_timezone: str) -> Optional[datetime]:
        """Parse natural language time string using unified time parser"""
        return time_parser.parse_natural_time(time_str, user_timezone)
    
    async def cleanup_expired_reminders(self) -> int:
        """Remove expired reminders from database"""
        current_time = time.time()
        cutoff_time = current_time - 3600  # 1 hour ago
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                DELETE FROM reminders WHERE timestamp < ?
            """, (cutoff_time,))
            
            deleted_count = cursor.rowcount
            await db.commit()
            
            if deleted_count > 0:
                logger.debug(f"Cleaned up {deleted_count} expired reminders from database")
                # Invalidate all caches since we can't know which users were affected
                await self._invalidate_cache()
            
            return deleted_count
    
    @io_bound
    async def _background_save_reminder(self, user_id: int, reminder_text: str, 
                                      trigger_time: float, timezone: str, channel_id: int = None) -> bool:
        """Background task for saving reminders"""
        try:
            async with self._get_connection() as db:
                await db.execute("""
                    INSERT INTO reminders (timestamp, user_id, message, timezone, created_at, channel_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (trigger_time, user_id, reminder_text, timezone, time.time(), channel_id))
                await db.commit()
                
                # Invalidate relevant caches
                await self._invalidate_cache(f"user_reminders_{user_id}")
                await self._invalidate_cache("next_reminder")
                
                return True
                
        except Exception as e:
            logger.error(f"Background save failed for reminder: {e}")
            return False
    
    @io_bound
    async def _background_delete_reminder(self, timestamp: float, user_id: int = None) -> bool:
        """Background task for deleting reminders"""
        try:
            async with self._get_connection() as db:
                if user_id:
                    await db.execute("DELETE FROM reminders WHERE timestamp = ? AND user_id = ?", 
                                   (timestamp, user_id))
                else:
                    await db.execute("DELETE FROM reminders WHERE timestamp = ?", (timestamp,))
                await db.commit()
                
                if user_id:
                    await self._invalidate_cache(f"user_reminders_{user_id}")
                await self._invalidate_cache("next_reminder")
                
                return True
                
        except Exception as e:
            logger.error(f"Background delete failed for reminder: {e}")
            return False
    
    @io_bound
    async def _background_cleanup_expired(self) -> int:
        """Background task for cleaning expired reminders"""
        try:
            return await self.cleanup_expired_reminders()
        except Exception as e:
            logger.error(f"Background cleanup failed: {e}")
            return 0
    
    # _background_save_timezone method removed - now using shared timezone_manager
    
    def add_dm_failed_user(self, user_id: int):
        """Mark a user as having DM failures"""
        self.dm_failed_users.add(user_id)
    
    def is_dm_failed_user(self, user_id: int) -> bool:
        """Check if user has DM failures"""
        return user_id in self.dm_failed_users
    
    async def get_reminder_event(self) -> asyncio.Event:
        """Get the event that signals when reminders are added"""
        return self._reminder_added_event
    
    async def wait_for_reminder_change(self):
        """Wait for a reminder to be added or modified"""
        await self._reminder_added_event.wait()
        self._reminder_added_event.clear()
    
    async def close(self):
        """Close all database connections and background tasks"""
        # Stop background task manager
        await background_task_manager.stop()
        
        # Close database connections
        async with self._pool_lock:
            for conn in self._connection_pool:
                await conn.close()
            self._connection_pool.clear()
        logger.info("Closed all database connections and background tasks")


# Create singleton instance
reminder_manager_v2 = ReminderManagerV2()