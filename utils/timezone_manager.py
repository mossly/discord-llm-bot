"""
Shared timezone management for reminders and tasks
Provides centralized timezone storage and retrieval
"""

import logging
import aiosqlite
import pytz
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEZONE = "Pacific/Auckland"  # New Zealand timezone (GMT+13)
DB_PATH = "/data/user_timezones.db"
CACHE_TTL = 300  # 5 minutes cache TTL


class TimezoneManager:
    """Manages user timezone preferences for the entire bot"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
    
    async def _get_connection(self):
        """Get database connection and ensure table exists"""
        db = await aiosqlite.connect(DB_PATH)
        await db.execute("PRAGMA foreign_keys = ON")
        
        # Create table if it doesn't exist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_timezones (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await db.commit()
        return db
    
    async def _get_cache(self, key: str) -> Optional[str]:
        """Get cached value if not expired"""
        if key in self._cache:
            if time.time() - self._cache_timestamps[key] < CACHE_TTL:
                return self._cache[key]
            else:
                # Expired, remove from cache
                del self._cache[key]
                del self._cache_timestamps[key]
        return None
    
    async def _set_cache(self, key: str, value: str):
        """Set cached value with timestamp"""
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()
    
    async def _invalidate_cache(self, key: str):
        """Remove key from cache"""
        if key in self._cache:
            del self._cache[key]
            del self._cache_timestamps[key]
    
    async def get_user_timezone(self, user_id: int) -> str:
        """Get a user's timezone or return default"""
        # Check cache first
        cache_key = f"user_timezone_{user_id}"
        cached_result = await self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        async with await self._get_connection() as db:
            cursor = await db.execute("""
                SELECT timezone FROM user_timezones WHERE user_id = ?
            """, (user_id,))
            
            row = await cursor.fetchone()
            timezone = row[0] if row else DEFAULT_TIMEZONE
            
            # Cache the result
            await self._set_cache(cache_key, timezone)
            
            return timezone
    
    async def set_user_timezone(self, user_id: int, timezone: str) -> tuple[bool, str]:
        """Set a user's timezone preference"""
        try:
            # Validate timezone
            pytz.timezone(timezone)
            
            async with await self._get_connection() as db:
                await db.execute("""
                    INSERT OR REPLACE INTO user_timezones (user_id, timezone, updated_at)
                    VALUES (?, ?, ?)
                """, (user_id, timezone, time.time()))
                await db.commit()
                
                # Invalidate cache
                await self._invalidate_cache(f"user_timezone_{user_id}")
                
                return True, f"Timezone set to {timezone}"
        except pytz.exceptions.UnknownTimeZoneError:
            return False, f"Unknown timezone: {timezone}"
        except Exception as e:
            logger.error(f"Failed to set timezone: {e}")
            return False, "Failed to save timezone"
    
    async def is_using_default_timezone(self, user_id: int) -> bool:
        """Check if user is using the default timezone"""
        user_tz = await self.get_user_timezone(user_id)
        return user_tz == DEFAULT_TIMEZONE


# Global instance
timezone_manager = TimezoneManager()

# Export for easy importing
__all__ = ['TimezoneManager', 'timezone_manager', 'DEFAULT_TIMEZONE']