"""
Reminder management tool for Discord bot LLM
Provides interface for LLM to manage user reminders
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import pytz
from .base_tool import BaseTool
from utils.reminder_manager import reminder_manager

logger = logging.getLogger(__name__)


class ReminderTool(BaseTool):
    """Tool for managing Discord bot reminders"""
    
    def __init__(self):
        super().__init__()
        self.reminder_manager = reminder_manager
    
    @property
    def name(self) -> str:
        return "manage_reminders"
    
    @property 
    def description(self) -> str:
        return "Manage Discord reminders for users. Can set, list, cancel reminders and get next reminder. Note: User's current local time is provided in the message context for accurate time calculations."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set", "list", "cancel", "next"],
                    "description": "Action to perform: 'set' (create reminder), 'list' (show all), 'cancel' (remove), 'next' (show next upcoming)"
                },
                "reminder_text": {
                    "type": "string",
                    "description": "Text for the reminder (required for 'set' action)"
                },
                "time_str": {
                    "type": "string",
                    "description": "Natural language time for the reminder (required for 'set' action). Examples: 'tomorrow at 3pm', 'in 2 hours', 'in 30 seconds', 'next Friday at 9am'"
                },
                "reminder_timestamp": {
                    "type": "number",
                    "description": "Unix timestamp of the reminder to cancel (required for 'cancel' action)"
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, action: str, user_id: str, reminder_text: str = None, 
                     time_str: str = None, reminder_timestamp: float = None) -> Dict[str, Any]:
        """Execute reminder management actions"""
        try:
            # Convert user_id to int for consistency
            try:
                user_id = int(user_id)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid user_id format: {user_id}. Must be a Discord user ID (numeric)"
                }
            
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
        
        # Get user's timezone
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        # Parse natural language time
        logger.info(f"Parsing time '{time_str}' for user {user_id} in timezone {user_timezone}")
        target_dt = self.reminder_manager.parse_natural_time(time_str, user_timezone)
        if not target_dt:
            logger.warning(f"Failed to parse time string: '{time_str}' for user {user_id}")
            return {
                "success": False,
                "error": f"Could not parse time: {time_str}. Try formats like 'tomorrow at 3pm', 'in 2 hours', 'in 30 seconds', 'next Friday at 9am'"
            }
        
        logger.info(f"Parsed time '{time_str}' as {target_dt} ({target_dt.tzinfo})")
        
        # Convert to UTC timestamp
        utc_dt = target_dt.astimezone(pytz.UTC)
        trigger_time = utc_dt.timestamp()
        
        # Add the reminder
        logger.info(f"Adding reminder for user {user_id} at timestamp {trigger_time} ({datetime.utcfromtimestamp(trigger_time)} UTC)")
        success, message = await self.reminder_manager.add_reminder(user_id, reminder_text, trigger_time, user_timezone)
        
        logger.info(f"Reminder add result: success={success}, message='{message}'")
        if success:
            # Format response
            readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
            return {
                "success": True,
                "message": f"Reminder set for {readable_time}",
                "reminder": {
                    "text": reminder_text,
                    "time": readable_time,
                    "timestamp": trigger_time,
                    "timezone": user_timezone
                }
            }
        else:
            return {
                "success": False,
                "error": message
            }
    
    async def _list_reminders(self, user_id: int) -> Dict[str, Any]:
        """List all reminders for a user"""
        user_reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        if not user_reminders:
            return {
                "success": True,
                "message": "No reminders found",
                "reminders": []
            }
        
        # Get user timezone
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        # Format reminders
        formatted_reminders = []
        for timestamp, message, _ in user_reminders:
            utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
            local_time = utc_time.astimezone(pytz.timezone(user_timezone))
            
            formatted_reminders.append({
                "text": message,
                "time": local_time.strftime("%A, %B %d at %I:%M %p"),
                "timestamp": timestamp,
                "time_until": self._format_time_until(utc_time)
            })
        
        return {
            "success": True,
            "message": f"Found {len(formatted_reminders)} reminder(s)",
            "reminders": formatted_reminders,
            "timezone": user_timezone
        }
    
    async def _cancel_reminder(self, user_id: int, reminder_timestamp: float) -> Dict[str, Any]:
        """Cancel a specific reminder"""
        if not reminder_timestamp:
            return {
                "success": False,
                "error": "Reminder timestamp is required for cancellation"
            }
        
        success, message = await self.reminder_manager.cancel_reminder(user_id, reminder_timestamp)
        
        return {
            "success": success,
            "message": message if success else None,
            "error": message if not success else None
        }
    
    async def _get_next_reminder(self, user_id: int) -> Dict[str, Any]:
        """Get the next upcoming reminder"""
        user_reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        if not user_reminders:
            return {
                "success": True,
                "message": "No upcoming reminders",
                "next_reminder": None
            }
        
        # Get the next reminder (first in sorted list)
        next_timestamp, next_message, _ = user_reminders[0]
        
        # Get user timezone
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        # Format the reminder
        utc_time = datetime.utcfromtimestamp(next_timestamp).replace(tzinfo=pytz.UTC)
        local_time = utc_time.astimezone(pytz.timezone(user_timezone))
        
        return {
            "success": True,
            "message": "Next reminder found",
            "next_reminder": {
                "text": next_message,
                "time": local_time.strftime("%A, %B %d at %I:%M %p"),
                "timestamp": next_timestamp,
                "time_until": self._format_time_until(utc_time),
                "timezone": user_timezone
            }
        }
    
    def _format_time_until(self, target_dt: datetime) -> str:
        """Format the time until a future datetime"""
        now = datetime.now(pytz.UTC)
        delta = target_dt - now
        
        if delta.total_seconds() < 0:
            return "now"
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 and days == 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        
        if not parts:
            return "in a moment"
        elif len(parts) == 1:
            return f"in {parts[0]}"
        else:
            return f"in {' and '.join(parts[:2])}"