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
                    "enum": ["set", "list", "cancel", "next", "search", "cancel_multiple", "update"],
                    "description": "Action to perform: 'set' to create reminder, 'list' to show all reminders, 'cancel' to remove specific reminder, 'next' to get next upcoming reminder, 'search' to find reminders by content, 'cancel_multiple' to remove multiple reminders, 'update' to modify existing reminder"
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
                },
                "search_query": {
                    "type": "string",
                    "description": "Text to search for in reminder content (required for 'search' action)"
                },
                "timestamps": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Array of Unix timestamps to cancel (required for 'cancel_multiple' action)"
                },
                "new_text": {
                    "type": "string",
                    "description": "New reminder text (required for 'update' action)"
                },
                "new_time": {
                    "type": "string",
                    "description": "New reminder time (required for 'update' action)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of reminders to return (optional for 'list' and 'search', default: 10)"
                }
            },
            "required": ["action", "user_id"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the reminder tool based on the action specified"""
        try:
            # Convert kwargs to parameters dict for consistency
            parameters = kwargs
            
            # Debug logging to track parameter issues
            logger.info(f"Reminder tool parameters: {parameters}")
            
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
                return await self._list_reminders(user_id, parameters)
            elif action == "cancel":
                return await self._cancel_reminder(user_id, parameters)
            elif action == "next":
                return await self._get_next_reminder(user_id)
            elif action == "search":
                return await self._search_reminders(user_id, parameters)
            elif action == "cancel_multiple":
                return await self._cancel_multiple_reminders(user_id, parameters)
            elif action == "update":
                return await self._update_reminder(user_id, parameters)
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
        
        # Check for common parameter mistakes
        if parameters.get("timestamp") and not time_str:
            logger.warning(f"AI incorrectly passed 'timestamp' instead of 'time' for set action: {parameters}")
            return {
                "success": False, 
                "message": "For setting reminders, use 'time' parameter with natural language (e.g. 'in 5 minutes'), not 'timestamp'. The 'timestamp' parameter is only for canceling reminders."
            }
        
        if not reminder_text:
            return {"success": False, "message": "reminder_text is required for set action"}
        
        if not time_str:
            return {"success": False, "message": "time is required for set action (use natural language like 'in 5 minutes', 'tomorrow at 3pm')"}
        
        # Ensure background task manager is running
        from utils.background_task_manager import background_task_manager
        if not background_task_manager.running:
            logger.info("Background task manager not running, starting it")
            await background_task_manager.start()
        
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
            
            # Check if user is using default timezone and add helpful message
            from utils.timezone_manager import DEFAULT_TIMEZONE
            message_text = f"Reminder set for {readable_time}{location}: {reminder_text}"
            if user_timezone == DEFAULT_TIMEZONE:
                message_text += f"\n\n💡 *Tip: You're using the default timezone ({DEFAULT_TIMEZONE}). Set your local timezone with `/timezone set` for more accurate times.*"
            
            return {
                "success": True,
                "message": message_text,
                "timestamp": trigger_time,
                "readable_time": readable_time
            }
        else:
            return {"success": False, "message": message}
    
    async def _list_reminders(self, user_id: int, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all reminders for the user"""
        if parameters is None:
            parameters = {}
        
        limit = parameters.get("limit", 10)
        reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        # Apply limit
        if limit and len(reminders) > limit:
            reminders = reminders[:limit]
        
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
    
    async def _search_reminders(self, user_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Search reminders by content"""
        search_query = parameters.get("search_query")
        
        if not search_query:
            return {"success": False, "message": "search_query is required for search action"}
        
        limit = parameters.get("limit", 10)
        all_reminders = await self.reminder_manager.get_user_reminders(user_id)
        
        # Filter reminders containing search query
        matching_reminders = []
        for timestamp, message, timezone, channel_id in all_reminders:
            if search_query.lower() in message.lower():
                matching_reminders.append((timestamp, message, timezone, channel_id))
        
        # Apply limit
        if limit and len(matching_reminders) > limit:
            matching_reminders = matching_reminders[:limit]
        
        if not matching_reminders:
            return {
                "success": True,
                "message": f"No reminders found matching '{search_query}'",
                "reminders": []
            }
        
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        formatted_reminders = []
        
        for timestamp, message, _, channel_id in matching_reminders:
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
            "message": f"Found {len(matching_reminders)} reminder(s) matching '{search_query}'",
            "reminders": formatted_reminders
        }
    
    async def _cancel_multiple_reminders(self, user_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel multiple reminders by timestamps"""
        timestamps = parameters.get("timestamps")
        
        if not timestamps or not isinstance(timestamps, list):
            return {"success": False, "message": "timestamps array is required for cancel_multiple action"}
        
        cancelled_count = 0
        cancelled_messages = []
        errors = []
        
        for timestamp in timestamps:
            try:
                success, message = await self.reminder_manager.cancel_reminder(user_id, float(timestamp))
                if success:
                    cancelled_count += 1
                    cancelled_messages.append(message)
                else:
                    errors.append(f"Timestamp {timestamp}: {message}")
            except Exception as e:
                errors.append(f"Timestamp {timestamp}: {str(e)}")
        
        if cancelled_count > 0:
            result_message = f"Successfully cancelled {cancelled_count} reminder(s)"
            if errors:
                result_message += f". {len(errors)} failed: {'; '.join(errors[:3])}"
                if len(errors) > 3:
                    result_message += f" and {len(errors) - 3} more"
            
            return {
                "success": True,
                "message": result_message,
                "cancelled_count": cancelled_count,
                "cancelled_reminders": cancelled_messages
            }
        else:
            return {
                "success": False,
                "message": f"Failed to cancel any reminders. Errors: {'; '.join(errors[:3])}"
            }
    
    async def _update_reminder(self, user_id: int, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing reminder"""
        timestamp = parameters.get("timestamp")
        new_text = parameters.get("new_text")
        new_time = parameters.get("new_time")
        
        if timestamp is None:
            return {"success": False, "message": "timestamp is required for update action"}
        
        if not new_text and not new_time:
            return {"success": False, "message": "Either new_text or new_time is required for update action"}
        
        # Get existing reminder
        reminders = await self.reminder_manager.get_user_reminders(user_id)
        existing_reminder = None
        
        for ts, msg, tz, channel_id in reminders:
            if ts == float(timestamp):
                existing_reminder = (ts, msg, tz, channel_id)
                break
        
        if not existing_reminder:
            return {"success": False, "message": "Reminder not found"}
        
        # Cancel the old reminder
        cancel_success, cancel_message = await self.reminder_manager.cancel_reminder(user_id, float(timestamp))
        if not cancel_success:
            return {"success": False, "message": f"Failed to cancel original reminder: {cancel_message}"}
        
        # Prepare new reminder data
        old_ts, old_msg, old_tz, old_channel_id = existing_reminder
        updated_text = new_text if new_text else old_msg
        user_timezone = await self.reminder_manager.get_user_timezone(user_id)
        
        if new_time:
            # Parse new time
            target_dt = self.reminder_manager.parse_natural_time(new_time, user_timezone)
            if not target_dt:
                # Restore the old reminder if time parsing failed
                await self.reminder_manager.add_reminder(user_id, old_msg, old_ts, old_tz, old_channel_id)
                return {
                    "success": False,
                    "message": f"Could not parse new time '{new_time}'. Original reminder restored."
                }
            
            # Convert to UTC timestamp
            utc_dt = target_dt.astimezone(pytz.UTC)
            new_timestamp = utc_dt.timestamp()
        else:
            new_timestamp = old_ts
        
        # Add the updated reminder
        add_success, add_message = await self.reminder_manager.add_reminder(
            user_id, updated_text, new_timestamp, user_timezone, old_channel_id
        )
        
        if add_success:
            if new_time:
                target_dt = datetime.fromtimestamp(new_timestamp, tz=pytz.timezone(user_timezone))
                readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
                location = f" in <#{old_channel_id}>" if old_channel_id else " via DM"
                return {
                    "success": True,
                    "message": f"Reminder updated: {updated_text} for {readable_time}{location}",
                    "timestamp": new_timestamp,
                    "readable_time": readable_time
                }
            else:
                return {
                    "success": True,
                    "message": f"Reminder text updated: {updated_text}",
                    "timestamp": new_timestamp
                }
        else:
            # Try to restore the original reminder if update failed
            await self.reminder_manager.add_reminder(user_id, old_msg, old_ts, old_tz, old_channel_id)
            return {
                "success": False,
                "message": f"Failed to update reminder: {add_message}. Original reminder restored."
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