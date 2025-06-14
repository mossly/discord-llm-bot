"""
Unified reminder management system for Discord LLM bot
Provides a single source of truth for all reminder operations
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set
import pytz

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

logger = logging.getLogger(__name__)

# Constants
MAX_REMINDERS_PER_USER = 25
MIN_REMINDER_INTERVAL = 60  # Minimum 60 seconds between reminders
DEFAULT_TIMEZONE = "Pacific/Auckland"  # New Zealand timezone (GMT+13)


class ReminderManager:
    """Centralized reminder management system"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.reminders = {}  # {timestamp: (user_id, message, timezone)}
            self.user_timezones = {}  # {user_id: timezone_string}
            self.reminders_file = "/data/reminders.json"
            self.timezones_file = "/data/user_timezones.json"
            self.dm_failed_users = set()  # Track users with failed DMs
            
            # Debounced save state
            self._reminders_save_pending = False
            self._timezones_save_pending = False
            self._save_delay = 5.0  # 5 second debounce
            
            # Ensure data directory exists
            os.makedirs("/data", exist_ok=True)
            
            # Load existing data
            logger.info(f"Initializing ReminderManager instance {id(self)}")
            self._load_data()
    
    def _load_data(self):
        """Load reminders and timezones from disk"""
        self._load_timezones()
        self._load_reminders()
    
    def _load_timezones(self):
        """Load user timezones from disk"""
        if os.path.exists(self.timezones_file):
            try:
                with open(self.timezones_file, 'r') as f:
                    data = json.load(f)
                    self.user_timezones = {
                        int(uid): tz for uid, tz in data.items()
                    }
                logger.debug(f"Loaded {len(self.user_timezones)} user timezone preferences")
            except Exception as e:
                logger.error(f"Failed to load user timezones: {e}", exc_info=True)
                self.user_timezones = {}
        else:
            self.user_timezones = {}
    
    def _load_reminders(self):
        """Load reminders from disk"""
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r') as f:
                    data = json.load(f)
                    self.reminders = {
                        float(ts): (int(uid), msg, tz) 
                        for ts, (uid, msg, tz) in data.items()
                    }
                logger.debug(f"Loaded {len(self.reminders)} reminders from disk (instance: {id(self)})")
                    
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}", exc_info=True)
                self.reminders = {}
        else:
            self.reminders = {}
    
    def _save_reminders(self):
        """Save reminders to disk"""
        try:
            data = {
                str(ts): [uid, msg, tz] 
                for ts, (uid, msg, tz) in self.reminders.items()
            }
            with open(self.reminders_file, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Saved {len(self.reminders)} reminders (instance: {id(self)})")
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}", exc_info=True)
    
    async def _save_reminders_async(self):
        """Save reminders to disk asynchronously"""
        try:
            data = {
                str(ts): [uid, msg, tz] 
                for ts, (uid, msg, tz) in self.reminders.items()
            }
            
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(self.reminders_file, 'w') as f:
                    await f.write(json.dumps(data))
            else:
                # Fallback to sync I/O
                with open(self.reminders_file, 'w') as f:
                    json.dump(data, f)
                    
            logger.debug(f"Saved {len(self.reminders)} reminders (instance: {id(self)})")
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}", exc_info=True)
    
    async def _debounced_save_reminders(self):
        """Save reminders with debouncing to reduce I/O"""
        if self._reminders_save_pending:
            return
            
        self._reminders_save_pending = True
        await asyncio.sleep(self._save_delay)
        
        if self._reminders_save_pending:  # Still pending after delay
            await self._save_reminders_async()
            self._reminders_save_pending = False
    
    async def _save_timezones_async(self):
        """Save user timezones to disk asynchronously"""
        try:
            data = {
                str(uid): tz for uid, tz in self.user_timezones.items()
            }
            
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(self.timezones_file, 'w') as f:
                    await f.write(json.dumps(data))
            else:
                # Fallback to sync I/O
                with open(self.timezones_file, 'w') as f:
                    json.dump(data, f)
                    
            logger.debug(f"Saved {len(self.user_timezones)} user timezone preferences")
        except Exception as e:
            logger.error(f"Failed to save user timezones: {e}", exc_info=True)
    
    async def _debounced_save_timezones(self):
        """Save user timezones with debouncing to reduce I/O"""
        if self._timezones_save_pending:
            return
            
        self._timezones_save_pending = True
        await asyncio.sleep(self._save_delay)
        
        if self._timezones_save_pending:  # Still pending after delay
            await self._save_timezones_async()
            self._timezones_save_pending = False
    
    def _save_timezones(self):
        """Save user timezones to disk"""
        try:
            data = {
                str(uid): tz for uid, tz in self.user_timezones.items()
            }
            with open(self.timezones_file, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Saved {len(self.user_timezones)} user timezone preferences")
        except Exception as e:
            logger.error(f"Failed to save user timezones: {e}", exc_info=True)
    
    async def add_reminder(self, user_id: int, reminder_text: str, trigger_time: float, timezone: str) -> Tuple[bool, str]:
        """
        Add a new reminder
        
        Returns: (success, message)
        """
        async with self._lock:
            # Check if time is in the past
            if trigger_time <= time.time():
                return False, "Cannot set reminders for the past"
            
            # Check user's reminder count (more efficient)
            user_reminder_count = sum(1 for _, (uid, _, _) in self.reminders.items() if uid == user_id)
            if user_reminder_count >= MAX_REMINDERS_PER_USER:
                return False, f"You already have {MAX_REMINDERS_PER_USER} reminders set"
            
            # Check for duplicate at same time
            if trigger_time in self.reminders and self.reminders[trigger_time][0] == user_id:
                return False, "You already have a reminder at this exact time"
            
            # Add the reminder
            self.reminders[trigger_time] = (user_id, reminder_text, timezone)
            
            # Trigger debounced save
            asyncio.create_task(self._debounced_save_reminders())
            
            return True, "Reminder set successfully"
    
    async def get_user_reminders(self, user_id: int) -> List[Tuple[float, str, str]]:
        """Get all reminders for a user sorted by time"""
        async with self._lock:
            # More efficient filtering and sorting
            user_reminders = [
                (timestamp, message, tz)
                for timestamp, (uid, message, tz) in self.reminders.items()
                if uid == user_id
            ]
            
            return sorted(user_reminders, key=lambda x: x[0])
    
    async def cancel_reminder(self, user_id: int, timestamp: float) -> Tuple[bool, str]:
        """Cancel a specific reminder"""
        async with self._lock:
            if timestamp in self.reminders:
                reminder_uid, message, _ = self.reminders[timestamp]
                if reminder_uid == user_id:
                    self.reminders.pop(timestamp)
                    
                    # Trigger debounced save
                    asyncio.create_task(self._debounced_save_reminders())
                    
                    return True, f"Cancelled reminder: {message}"
                else:
                    return False, "You can only cancel your own reminders"
            else:
                return False, "Reminder not found"
    
    async def get_due_reminders(self) -> List[Tuple[float, int, str, str]]:
        """Get all reminders that are due (past current time)"""
        async with self._lock:
            current_time = time.time()
            due_reminders = []
            
            # Use a more efficient approach with sorted keys if we have many reminders
            if len(self.reminders) > 100:
                # For large reminder sets, use sorted approach
                sorted_timestamps = sorted(self.reminders.keys())
                for trigger_time in sorted_timestamps:
                    if trigger_time <= current_time:
                        user_id, message, timezone = self.reminders[trigger_time]
                        due_reminders.append((trigger_time, user_id, message, timezone))
                    else:
                        # Since timestamps are sorted, we can break early
                        break
            else:
                # For small reminder sets, use the original approach
                for trigger_time, (user_id, message, timezone) in list(self.reminders.items()):
                    if trigger_time <= current_time:
                        due_reminders.append((trigger_time, user_id, message, timezone))
            
            return due_reminders
    
    async def get_next_reminder_time(self) -> Optional[float]:
        """Get the timestamp of the next upcoming reminder"""
        async with self._lock:
            if not self.reminders:
                return None
            
            current_time = time.time()
            future_reminders = [ts for ts in self.reminders.keys() if ts > current_time]
            
            if not future_reminders:
                return None
                
            return min(future_reminders)
    
    async def cleanup_expired_reminders(self) -> int:
        """Remove expired reminders from memory to prevent memory bloat"""
        async with self._lock:
            current_time = time.time()
            # Keep a 1-hour buffer to account for any delays
            cutoff_time = current_time - 3600  # 1 hour ago
            
            expired_timestamps = [
                ts for ts in self.reminders.keys() 
                if ts < cutoff_time
            ]
            
            for ts in expired_timestamps:
                self.reminders.pop(ts, None)
            
            if expired_timestamps:
                logger.debug(f"Cleaned up {len(expired_timestamps)} expired reminders from memory")
                # Trigger a save to persist the cleanup
                asyncio.create_task(self._debounced_save_reminders())
            
            return len(expired_timestamps)
    
    async def mark_reminder_sent(self, timestamp: float):
        """Remove a reminder after it has been sent"""
        async with self._lock:
            self.reminders.pop(timestamp, None)
            
            # Trigger debounced save
            asyncio.create_task(self._debounced_save_reminders())
    
    async def set_user_timezone(self, user_id: int, timezone: str) -> Tuple[bool, str]:
        """Set a user's timezone preference"""
        async with self._lock:
            try:
                # Validate timezone
                pytz.timezone(timezone)
                self.user_timezones[user_id] = timezone
                
                # Trigger debounced save
                asyncio.create_task(self._debounced_save_timezones())
                
                return True, f"Timezone set to {timezone}"
            except pytz.exceptions.UnknownTimeZoneError:
                return False, f"Unknown timezone: {timezone}"
    
    async def get_user_timezone(self, user_id: int) -> str:
        """Get a user's timezone or return default"""
        async with self._lock:
            return self.user_timezones.get(user_id, DEFAULT_TIMEZONE)
    
    def parse_natural_time(self, time_str: str, user_timezone: str) -> Optional[datetime]:
        """
        Parse natural language time string
        
        Returns: datetime object in user's timezone or None if parsing fails
        """
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
    
    def add_dm_failed_user(self, user_id: int):
        """Mark a user as having DM failures"""
        self.dm_failed_users.add(user_id)
    
    def is_dm_failed_user(self, user_id: int) -> bool:
        """Check if user has DM failures"""
        return user_id in self.dm_failed_users


# Create singleton instance
reminder_manager = ReminderManager()