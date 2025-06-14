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

logger = logging.getLogger(__name__)

# Constants
MAX_REMINDERS_PER_USER = 25
MIN_REMINDER_INTERVAL = 60  # Minimum 60 seconds between reminders
DEFAULT_TIMEZONE = "Pacific/Auckland"  # New Zealand timezone (GMT+13)
DB_PATH = "/data/reminders.db"
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
            os.makedirs("/data", exist_ok=True)
            
            logger.info(f"Initializing ReminderManagerV2 instance {id(self)}")
    
    async def initialize(self):
        """Initialize the database and connection pool"""
        await self._init_database()
        await self._init_connection_pool()
        
        # Start background task manager
        await background_task_manager.start()
        
        # Migrate from old JSON-based system if needed
        await self._migrate_from_json()
    
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
            await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(timestamp) WHERE timestamp <= ?", (time.time(),))
            
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
        old_reminders_file = "/data/reminders.json"
        old_timezones_file = "/data/user_timezones.json"
        
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
    
    async def add_reminder(self, user_id: int, reminder_text: str, trigger_time: float, timezone: str) -> Tuple[bool, str]:
        """Add a new reminder"""
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
                    success = await background_task_manager.submit_function(
                        self._background_save_reminder,
                        user_id, reminder_text, trigger_time, timezone,
                        task_id=f"save_reminder_{user_id}_{int(trigger_time)}",
                        priority=TaskPriority.HIGH
                    )
                    
                    if success:
                        # Signal that a reminder was added for event-driven processing
                        self._reminder_added_event.set()
                        return True, "Reminder set successfully"
                    else:
                        return False, "Failed to queue reminder for saving"
                    
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        return False, "You already have a reminder at this exact time"
                    logger.error(f"Failed to add reminder: {e}")
                    return False, "Failed to add reminder"
    
    async def get_user_reminders(self, user_id: int) -> List[Tuple[float, str, str]]:
        """Get all reminders for a user sorted by time"""
        # Check cache first
        cache_key = f"user_reminders_{user_id}"
        cached_result = await self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timestamp, message, timezone
                FROM reminders
                WHERE user_id = ?
                ORDER BY timestamp ASC
            """, (user_id,))
            
            reminders = [(row['timestamp'], row['message'], row['timezone']) 
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
    
    async def get_due_reminders(self) -> List[Tuple[float, int, str, str]]:
        """Get all reminders that are due (past current time)"""
        current_time = time.time()
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timestamp, user_id, message, timezone
                FROM reminders
                WHERE timestamp <= ?
                ORDER BY timestamp ASC
            """, (current_time,))
            
            return [(row['timestamp'], row['user_id'], row['message'], row['timezone'])
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
        """Set a user's timezone preference"""
        async with self._lock:
            try:
                # Validate timezone
                pytz.timezone(timezone)
                
                # Use background task for timezone saving
                success = await background_task_manager.submit_function(
                    self._background_save_timezone,
                    user_id, timezone,
                    task_id=f"save_timezone_{user_id}",
                    priority=TaskPriority.NORMAL
                )
                
                if success:
                    return True, f"Timezone set to {timezone}"
                else:
                    return False, "Failed to save timezone"
                
            except pytz.exceptions.UnknownTimeZoneError:
                return False, f"Unknown timezone: {timezone}"
    
    async def get_user_timezone(self, user_id: int) -> str:
        """Get a user's timezone or return default"""
        # Check cache first
        cache_key = f"user_timezone_{user_id}"
        cached_result = await self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timezone FROM user_timezones WHERE user_id = ?
            """, (user_id,))
            
            row = await cursor.fetchone()
            timezone = row['timezone'] if row else DEFAULT_TIMEZONE
            
            # Cache the result
            await self._set_cache(cache_key, timezone)
            
            return timezone
    
    def parse_natural_time(self, time_str: str, user_timezone: str) -> Optional[datetime]:
        """Parse natural language time string (unchanged from v1)"""
        try:
            local_tz = pytz.timezone(user_timezone)
            now = datetime.now(local_tz)
            time_str = time_str.lower().strip()
            
            # Handle special keywords
            if time_str == "tomorrow":
                return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            elif time_str == "tonight":
                return now.replace(hour=20, minute=0, second=0, microsecond=0)
            elif time_str == "noon" or time_str == "midday":
                if now.hour >= 12:
                    return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
                else:
                    return now.replace(hour=12, minute=0, second=0, microsecond=0)
            elif time_str == "midnight":
                return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Handle "in X minutes/hours/days" and "X minutes from now" patterns
            relative_patterns = [
                ("in ", 3),           # "in 5 minutes"
                ("", 0),              # Handle "X minutes from now" and other patterns
            ]
            
            for prefix, prefix_len in relative_patterns:
                if prefix and not time_str.startswith(prefix):
                    continue
                    
                remaining = time_str[prefix_len:].strip()
                
                # Handle "X minutes from now", "X mins from now", etc.
                if "from now" in remaining:
                    remaining = remaining.replace("from now", "").strip()
                
                # Handle "in about X", "around X", etc.
                remaining = remaining.replace("about ", "").replace("around ", "").strip()
                
                # Handle informal patterns like "a minute", "a few minutes"
                if remaining in ["a minute", "1 minute"]:
                    return now + timedelta(minutes=1)
                elif remaining in ["a few minutes", "few minutes"]:
                    return now + timedelta(minutes=3)
                elif remaining in ["a second", "1 second"]:
                    return now + timedelta(seconds=1)
                elif remaining in ["a few seconds", "few seconds"]:
                    return now + timedelta(seconds=5)
                
                # Parse numerical patterns
                parts = remaining.split()
                if len(parts) >= 2:
                    try:
                        amount = int(parts[0])
                        unit = parts[1].rstrip('s').lower()
                        
                        # Handle common abbreviations and variations
                        unit_mapping = {
                            'second': 'seconds', 'sec': 'seconds', 's': 'seconds',
                            'minute': 'minutes', 'min': 'minutes', 'm': 'minutes',
                            'hour': 'hours', 'hr': 'hours', 'h': 'hours',
                            'day': 'days', 'd': 'days',
                            'week': 'weeks', 'w': 'weeks',
                            'month': 'months'
                        }
                        
                        unit = unit_mapping.get(unit, unit)
                        
                        if unit == 'seconds':
                            return now + timedelta(seconds=amount)
                        elif unit == 'minutes':
                            return now + timedelta(minutes=amount)
                        elif unit == 'hours':
                            return now + timedelta(hours=amount)
                        elif unit == 'days':
                            return now + timedelta(days=amount)
                        elif unit == 'weeks':
                            return now + timedelta(weeks=amount)
                        elif unit == 'months':
                            return now + timedelta(days=amount * 30)
                    except ValueError:
                        continue
                
                # If we found a matching prefix, don't try other patterns
                if prefix:
                    break
            
            # Handle "tomorrow at X"
            if "tomorrow" in time_str and "at" in time_str:
                time_part = time_str.split("at")[-1].strip()
                tomorrow = now + timedelta(days=1)
                
                # Parse time formats
                for fmt in ["%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"]:
                    try:
                        parsed_time = datetime.strptime(time_part.upper(), fmt)
                        return tomorrow.replace(
                            hour=parsed_time.hour, 
                            minute=parsed_time.minute, 
                            second=0, 
                            microsecond=0
                        )
                    except ValueError:
                        continue
            
            # Handle day names
            day_mapping = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
                "friday": 4, "saturday": 5, "sunday": 6
            }
            
            for day_name, day_num in day_mapping.items():
                if day_name in time_str:
                    current_day = now.weekday()
                    days_ahead = (day_num - current_day) % 7
                    
                    # Check if "next" is mentioned
                    is_next = "next" in time_str
                    
                    if days_ahead == 0:  # Today
                        if is_next or now.hour >= 12:
                            days_ahead = 7
                    
                    target_date = now + timedelta(days=days_ahead)
                    target_time = "9:00 AM"  # Default time
                    
                    # Extract time if specified
                    if "at" in time_str:
                        time_part = time_str.split("at")[-1].strip()
                        for fmt in ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]:
                            try:
                                parsed_time = datetime.strptime(time_part.upper(), fmt)
                                target_time = parsed_time.strftime("%H:%M")
                                break
                            except ValueError:
                                continue
                    
                    # Parse the final time
                    try:
                        hour, minute = map(int, target_time.split(":")[:2])
                        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except ValueError:
                        pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing natural time '{time_str}': {e}")
            return None
    
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
                                      trigger_time: float, timezone: str) -> bool:
        """Background task for saving reminders"""
        try:
            async with self._get_connection() as db:
                await db.execute("""
                    INSERT INTO reminders (timestamp, user_id, message, timezone, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (trigger_time, user_id, reminder_text, timezone, time.time()))
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
    
    @io_bound
    async def _background_save_timezone(self, user_id: int, timezone: str) -> bool:
        """Background task for saving user timezone"""
        try:
            async with self._get_connection() as db:
                await db.execute("""
                    INSERT OR REPLACE INTO user_timezones (user_id, timezone, updated_at)
                    VALUES (?, ?, ?)
                """, (user_id, timezone, time.time()))
                await db.commit()
                
                await self._invalidate_cache(f"user_timezone_{user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Background timezone save failed: {e}")
            return False
    
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