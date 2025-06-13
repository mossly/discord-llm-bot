"""
Reminder tool for LLMs to manage user reminders
"""

from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
import logging
import json
import os
import time
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

# Constants matching the reminder cog
MAX_REMINDERS_PER_USER = 25
DEFAULT_TIMEZONE = "Pacific/Auckland"


class ReminderTool(BaseTool):
    """Tool for managing Discord bot reminders"""
    
    def __init__(self):
        super().__init__()
        self.reminders_file = "data/reminders.json"
        self.timezones_file = "data/user_timezones.json"
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        self._load_data()
    
    @property
    def name(self) -> str:
        return "manage_reminders"
    
    @property
    def description(self) -> str:
        return """Manage reminders for users. You can set new reminders with natural language time parsing, list upcoming reminders, cancel specific reminders, or get the next reminder. 
        
        Actions:
        - set: Create a new reminder (e.g., "remind me to call mom tomorrow at 3pm")
        - list: Show all upcoming reminders
        - cancel: Cancel a reminder by its timestamp
        - next: Get the next upcoming reminder
        
        Time examples: "tomorrow at 3pm", "in 2 hours", "next Friday", "December 25th at noon"
        """
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set", "list", "cancel", "next"],
                    "description": "The action to perform with reminders"
                },
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (automatically set for security)"
                },
                "reminder_text": {
                    "type": "string",
                    "description": "Text for the reminder (required for 'set' action)"
                },
                "time_str": {
                    "type": "string",
                    "description": "Natural language time for the reminder (required for 'set' action). Examples: 'tomorrow at 3pm', 'in 2 hours', 'next Friday at 9am'"
                },
                "reminder_timestamp": {
                    "type": "number",
                    "description": "Unix timestamp of the reminder to cancel (required for 'cancel' action)"
                }
            },
            "required": ["action", "user_id"]
        }
    
    def _load_data(self):
        """Load reminders and timezones from disk"""
        # Load reminders
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r') as f:
                    data = json.load(f)
                    self.reminders = {
                        float(ts): (int(uid), msg, tz) 
                        for ts, (uid, msg, tz) in data.items()
                    }
                logger.info(f"Loaded {len(self.reminders)} reminders")
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}", exc_info=True)
                self.reminders = {}
        else:
            self.reminders = {}
        
        # Load user timezones
        if os.path.exists(self.timezones_file):
            try:
                with open(self.timezones_file, 'r') as f:
                    data = json.load(f)
                    self.user_timezones = {
                        int(uid): tz for uid, tz in data.items()
                    }
                logger.info(f"Loaded {len(self.user_timezones)} user timezones")
            except Exception as e:
                logger.error(f"Failed to load timezones: {e}", exc_info=True)
                self.user_timezones = {}
        else:
            self.user_timezones = {}
    
    def _save_reminders(self):
        """Save reminders to disk"""
        try:
            data = {
                str(ts): [uid, msg, tz] 
                for ts, (uid, msg, tz) in self.reminders.items()
            }
            with open(self.reminders_file, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved {len(self.reminders)} reminders")
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}", exc_info=True)
    
    def _get_user_timezone(self, user_id: int) -> str:
        """Get user's timezone or default"""
        return self.user_timezones.get(user_id, DEFAULT_TIMEZONE)
    
    def _parse_natural_time(self, time_str: str, user_timezone: str) -> Optional[datetime]:
        """Parse natural language time string"""
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
            
            # Handle "in X minutes/hours/days"
            elif time_str.startswith("in "):
                parts = time_str[3:].split()
                if len(parts) >= 2:
                    try:
                        amount = int(parts[0])
                        unit = parts[1].lower()
                        if unit.startswith("minute"):
                            return now + timedelta(minutes=amount)
                        elif unit.startswith("hour"):
                            return now + timedelta(hours=amount)
                        elif unit.startswith("day"):
                            return now + timedelta(days=amount)
                        elif unit.startswith("week"):
                            return now + timedelta(weeks=amount)
                        elif unit.startswith("month"):
                            return now + timedelta(days=30*amount)
                    except ValueError:
                        pass
            
            # Handle "tomorrow at X"
            elif "tomorrow" in time_str and ("at" in time_str or ":" in time_str):
                time_part = time_str.split("at")[-1].strip() if "at" in time_str else time_str.split("tomorrow")[-1].strip()
                time_part = time_part.replace("am", " AM").replace("pm", " PM")
                
                time_formats = ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]
                parsed_time = None
                
                for fmt in time_formats:
                    try:
                        parsed_time = datetime.strptime(time_part, fmt)
                        break
                    except ValueError:
                        continue
                
                if parsed_time:
                    tomorrow = now + timedelta(days=1)
                    return tomorrow.replace(
                        hour=parsed_time.hour, 
                        minute=parsed_time.minute, 
                        second=0, 
                        microsecond=0
                    )
            
            # Handle day names
            elif any(day in time_str.lower() for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
                day_mapping = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                
                target_day = None
                for day, day_num in day_mapping.items():
                    if day in time_str.lower():
                        target_day = day_num
                        break
                
                if target_day is not None:
                    current_day = now.weekday()
                    days_ahead = (target_day - current_day) % 7
                    
                    is_next_mentioned = "next" in time_str.lower()
                    
                    if days_ahead == 0:
                        if is_next_mentioned or now.hour >= 12:
                            days_ahead = 7
                    
                    target_date = now + timedelta(days=days_ahead)
                    target_time = "9:00 AM"
                    
                    # Try to extract time if specified
                    if "at" in time_str:
                        time_part = time_str.split("at")[-1].strip()
                        time_part = time_part.replace("am", " AM").replace("pm", " PM")
                        
                        time_formats = ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]
                        for fmt in time_formats:
                            try:
                                parsed_time = datetime.strptime(time_part, fmt)
                                target_time = parsed_time.strftime("%H:%M")
                                break
                            except ValueError:
                                continue
                    
                    try:
                        hour, minute = map(int, target_time.split(":")[:2])
                        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except ValueError:
                        pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing time string '{time_str}': {e}")
            return None
    
    def _format_time_until(self, target_dt: datetime) -> str:
        """Format time until reminder"""
        now = datetime.now()
        delta = target_dt - now
        
        if delta.total_seconds() <= 0:
            return "now"
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 and not days:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        
        if not parts:
            return "in a moment"
        else:
            return f"in {' and '.join(parts[:2])}"
    
    async def execute(self, action: str, user_id: str, reminder_text: str = None, 
                     time_str: str = None, reminder_timestamp: float = None) -> Dict[str, Any]:
        """Execute reminder management actions"""
        try:
            # Convert user_id to int for consistency
            user_id = int(user_id)
            
            # Reload data to ensure we have latest state
            self._load_data()
            
            if action == "set":
                return await self._set_reminder(user_id, reminder_text, time_str)
            elif action == "list":
                return await self._list_reminders(user_id)
            elif action == "cancel":
                return await self._cancel_reminder(user_id, reminder_timestamp)
            elif action == "next":
                return await self._get_next_reminder(user_id)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }
                
        except Exception as e:
            logger.error(f"Error executing reminder tool: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _set_reminder(self, user_id: int, reminder_text: str, time_str: str) -> Dict[str, Any]:
        """Set a new reminder"""
        if not reminder_text:
            return {
                "success": False,
                "error": "Reminder text is required"
            }
        
        if not time_str:
            return {
                "success": False,
                "error": "Time is required"
            }
        
        # Check user's reminder count
        user_reminders = [r for t, (uid, r, _) in self.reminders.items() if uid == user_id]
        if len(user_reminders) >= MAX_REMINDERS_PER_USER:
            return {
                "success": False,
                "error": f"You already have {MAX_REMINDERS_PER_USER} reminders. Please cancel some before adding more.",
                "current_count": len(user_reminders)
            }
        
        # Get user timezone and parse time
        user_timezone = self._get_user_timezone(user_id)
        local_tz = pytz.timezone(user_timezone)
        
        # Parse natural language time
        target_dt = self._parse_natural_time(time_str, user_timezone)
        
        if not target_dt:
            return {
                "success": False,
                "error": f"Could not parse time '{time_str}'. Try formats like 'tomorrow at 3pm', 'in 2 hours', or 'next Friday'."
            }
        
        # Convert to UTC for storage
        utc_dt = target_dt.astimezone(pytz.UTC)
        trigger_time = utc_dt.timestamp()
        
        # Check if in the past
        if trigger_time <= time.time():
            return {
                "success": False,
                "error": "Cannot set reminders for the past. Please choose a future time."
            }
        
        # Check for duplicate at same time
        if trigger_time in self.reminders and self.reminders[trigger_time][0] == user_id:
            return {
                "success": False,
                "error": "You already have a reminder at this exact time."
            }
        
        # Add the reminder
        self.reminders[trigger_time] = (user_id, reminder_text, user_timezone)
        self._save_reminders()
        
        # Format response
        readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
        time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
        
        return {
            "success": True,
            "message": f"Reminder set for {readable_time} ({time_until})",
            "reminder": {
                "text": reminder_text,
                "time": readable_time,
                "time_until": time_until,
                "timestamp": trigger_time,
                "timezone": user_timezone
            }
        }
    
    async def _list_reminders(self, user_id: int) -> Dict[str, Any]:
        """List all reminders for a user"""
        user_reminders = [
            (ts, msg, tz) for ts, (uid, msg, tz) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            return {
                "success": True,
                "reminders": [],
                "message": "You have no upcoming reminders."
            }
        
        # Sort by timestamp
        user_reminders.sort(key=lambda x: x[0])
        
        # Get user timezone
        user_timezone = self._get_user_timezone(user_id)
        local_tz = pytz.timezone(user_timezone)
        
        # Format reminders
        formatted_reminders = []
        for ts, msg, _ in user_reminders:
            utc_dt = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)
            local_dt = utc_dt.astimezone(local_tz)
            readable_time = local_dt.strftime("%A, %B %d at %I:%M %p")
            time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
            
            formatted_reminders.append({
                "text": msg,
                "time": readable_time,
                "time_until": time_until,
                "timestamp": ts
            })
        
        return {
            "success": True,
            "reminders": formatted_reminders,
            "count": len(formatted_reminders),
            "timezone": user_timezone
        }
    
    async def _cancel_reminder(self, user_id: int, reminder_timestamp: float) -> Dict[str, Any]:
        """Cancel a specific reminder"""
        if not reminder_timestamp:
            return {
                "success": False,
                "error": "Reminder timestamp is required"
            }
        
        # Check if reminder exists and belongs to user
        if reminder_timestamp not in self.reminders:
            return {
                "success": False,
                "error": "Reminder not found"
            }
        
        reminder_user_id, reminder_text, _ = self.reminders[reminder_timestamp]
        if reminder_user_id != user_id:
            return {
                "success": False,
                "error": "You can only cancel your own reminders"
            }
        
        # Remove the reminder
        self.reminders.pop(reminder_timestamp)
        self._save_reminders()
        
        return {
            "success": True,
            "message": f"Reminder cancelled: {reminder_text}"
        }
    
    async def _get_next_reminder(self, user_id: int) -> Dict[str, Any]:
        """Get the next upcoming reminder"""
        user_reminders = [
            (ts, msg, tz) for ts, (uid, msg, tz) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            return {
                "success": True,
                "next_reminder": None,
                "message": "You have no upcoming reminders."
            }
        
        # Get the earliest reminder
        next_reminder = min(user_reminders, key=lambda x: x[0])
        ts, msg, _ = next_reminder
        
        # Get user timezone
        user_timezone = self._get_user_timezone(user_id)
        local_tz = pytz.timezone(user_timezone)
        
        # Format time
        utc_dt = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)
        local_dt = utc_dt.astimezone(local_tz)
        readable_time = local_dt.strftime("%A, %B %d at %I:%M %p")
        time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
        
        return {
            "success": True,
            "next_reminder": {
                "text": msg,
                "time": readable_time,
                "time_until": time_until,
                "timestamp": ts
            },
            "timezone": user_timezone
        }