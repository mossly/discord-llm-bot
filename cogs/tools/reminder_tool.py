"""
Reminder management tool for Discord bot LLM
Provides interface for LLM to manage user reminders
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import pytz
from .base_tool import BaseTool
from utils.reminder_manager import reminder_manager_v2

logger = logging.getLogger(__name__)


class ReminderTool(BaseTool):
    """Tool for managing Discord bot reminders"""
    
    def __init__(self):
        super().__init__()
        self.reminder_manager = reminder_manager_v2
    
    @property
    def name(self) -> str:
        return "manage_reminders"
    
    @property 
    def description(self) -> str:
        return "Manage Discord reminders for users. Can set, list, cancel reminders and get next reminder. Note: User's current local time is provided in the message context for accurate time calculations."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["set", "list", "cancel", "next"],
                    "description": "Action to perform: 'set' to create reminder, 'list' to show all reminders, 'cancel' to remove reminder, 'next' to get next upcoming reminder"
                },
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (required for all actions)"
                },
                "reminder_text": {
                    "type": "string", 
                    "description": "Text of the reminder (required for 'set' action only)"
                },
                "time": {
                    "type": "string",
                    "description": "When to remind (required for 'set' action only). Can be natural language like 'tomorrow at 3pm', 'in 2 hours', 'Friday 9am', or specific format 'YYYY-MM-DD HH:MM'"
                },
                "timestamp": {
                    "type": "number",
                    "description": "Unix timestamp of reminder to cancel (required for 'cancel' action only)"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Discord channel ID where reminder should be sent (optional for 'set' action, defaults to DM)"
                }
            },
            "required": ["action", "user_id"]
        }
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the reminder tool based on the action specified"""
        try:
            action = parameters.get("action")
            user_id_str = parameters.get("user_id")
            
            if not user_id_str:
                return {"success": False, "message": "user_id is required"}
            
            try:
                user_id = int(user_id_str)
            except ValueError:
                return {"success": False, "message": "user_id must be a valid number"}
            
            if action == "set":
                return await self._set_reminder(user_id, parameters)
            elif action == "list":
                return await self._list_reminders(user_id)
            elif action == "cancel":
                return await self._cancel_reminder(user_id, parameters)
            elif action == "next":
                return await self._get_next_reminder(user_id)
            else:
                return {"success": False, "message": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error in reminder tool: {e}", exc_info=True)
            return {"success": False, "message": f"An error occurred: {str(e)}"}
    
    async def _set_reminder(self, user_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Set a new reminder"""
        reminder_text = parameters.get("reminder_text")
        time_str = parameters.get("time")
        channel_id_str = parameters.get("channel_id")
        
        if not reminder_text:
            return {"success": False, "message": "reminder_text is required for set action"}
        
        if not time_str:
            return {"success": False, "message": "time is required for set action"}
        
        # Parse channel_id if provided
        channel_id = None
        if channel_id_str:
            try:
                channel_id = int(channel_id_str)
            except ValueError:
                return {"success": False, "message": "channel_id must be a valid number"}
        
        # Get user's timezone
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        # Try to parse the time
        target_dt = self.reminder_manager.parse_natural_time(time_str, user_timezone)
        
        if not target_dt:
            return {
                "success": False, 
                "message": f"Could not parse time '{time_str}'. Try formats like 'tomorrow 3pm', 'in 2 hours', 'Friday 9am', or 'YYYY-MM-DD HH:MM'"
            }
        
        # Convert to UTC timestamp
        utc_dt = target_dt.astimezone(pytz.UTC)
        trigger_time = utc_dt.timestamp()
        
        # Set the reminder
        success, message = await self.reminder_manager.add_reminder(
            user_id, reminder_text, trigger_time, user_timezone, channel_id
        )
        
        if success:
            readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
            location = f" in <#{channel_id}>" if channel_id else " via DM"
            return {
                "success": True,
                "message": f"Reminder set for {readable_time}{location}: {reminder_text}",
                "timestamp": trigger_time,
                "readable_time": readable_time
            }
        else:
            return {"success": False, "message": message}
    
    async def _list_reminders(self, user_id: int) -> Dict[str, Any]:
        """List all reminders for the user"""
        reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        if not reminders:
            return {
                "success": True,
                "message": "No reminders found",
                "reminders": []
            }
        
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        formatted_reminders = []
        
        for timestamp, message, _, channel_id in reminders:
            utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
            local_time = utc_time.astimezone(pytz.timezone(user_timezone))
            readable_time = local_time.strftime("%A, %B %d at %I:%M %p")
            
            location = f"Channel <#{channel_id}>" if channel_id else "Direct Message"
            
            formatted_reminders.append({
                "timestamp": timestamp,
                "message": message,
                "readable_time": readable_time,
                "location": location
            })
        
        return {
            "success": True,
            "message": f"Found {len(reminders)} reminder(s)",
            "reminders": formatted_reminders
        }
    
    async def _cancel_reminder(self, user_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a specific reminder"""
        timestamp = parameters.get("timestamp")
        
        if timestamp is None:
            return {"success": False, "message": "timestamp is required for cancel action"}
        
        success, message = await self.reminder_manager.cancel_reminder(user_id, float(timestamp))
        return {"success": success, "message": message}
    
    async def _get_next_reminder(self, user_id: int) -> Dict[str, Any]:
        """Get the user's next upcoming reminder"""
        reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        if not reminders:
            return {
                "success": True,
                "message": "No upcoming reminders",
                "next_reminder": None
            }
        
        # Get the first (next) reminder
        timestamp, message, _, channel_id = reminders[0]
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
        local_time = utc_time.astimezone(pytz.timezone(user_timezone))
        readable_time = local_time.strftime("%A, %B %d at %I:%M %p")
        
        location = f"Channel <#{channel_id}>" if channel_id else "Direct Message"
        
        return {
            "success": True,
            "message": f"Next reminder: {message}",
            "next_reminder": {
                "timestamp": timestamp,
                "message": message,
                "readable_time": readable_time,
                "location": location
            }
        }