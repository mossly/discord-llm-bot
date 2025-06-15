import logging
import time
from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import pytz

from .base_tool import BaseTool
from utils.task_manager import TaskManager, Task, TaskStatus, TaskPriorityLevel, RecurrenceType

logger = logging.getLogger(__name__)

class TaskManagementTool(BaseTool):
    """Tool for AI to interact with the task management system"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "task_management"
        self._description = "Manage tasks including creating, viewing, updating, and completing tasks for users"
        
    @property
    def name(self) -> str:
        return self._name
        
    @property
    def description(self) -> str:
        return self._description
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create_task",
                        "get_task",
                        "update_task", 
                        "delete_task",
                        "complete_task",
                        "list_user_tasks",
                        "get_overdue_tasks",
                        "get_upcoming_tasks",
                        "search_tasks"
                    ],
                    "description": "The action to perform on tasks"
                },
                "user_id": {
                    "type": "integer",
                    "description": "Discord user ID for the task operation"
                },
                "task_id": {
                    "type": "integer",
                    "description": "Task ID for operations on specific tasks"
                },
                "title": {
                    "type": "string",
                    "description": "Task title (required for create_task)"
                },
                "description": {
                    "type": "string", 
                    "description": "Task description (optional)"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in ISO format or natural language (e.g., 'tomorrow 3pm')"
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"],
                    "description": "Task priority level"
                },
                "category": {
                    "type": "string",
                    "description": "Task category (e.g., 'Work', 'Personal')"
                },
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "OVERDUE", "CANCELLED"],
                    "description": "Task status"
                },
                "channel_id": {
                    "type": "integer",
                    "description": "Discord channel ID where task was created"
                },
                "timezone": {
                    "type": "string",
                    "description": "User's timezone (default: UTC)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tasks to return (default: 10)"
                },
                "hours_ahead": {
                    "type": "integer",
                    "description": "Hours to look ahead for upcoming tasks (default: 24)"
                },
                "search_query": {
                    "type": "string",
                    "description": "Search query for task titles and descriptions"
                }
            },
            "required": ["action", "user_id"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute task management operations"""
        try:
            action = kwargs.get("action")
            user_id = kwargs.get("user_id")
            
            if not action or not user_id:
                return {"error": "Missing required parameters: action and user_id"}
                
            # Route to appropriate method
            if action == "create_task":
                return await self._create_task(**kwargs)
            elif action == "get_task":
                return await self._get_task(**kwargs)
            elif action == "update_task":
                return await self._update_task(**kwargs)
            elif action == "delete_task":
                return await self._delete_task(**kwargs)
            elif action == "complete_task":
                return await self._complete_task(**kwargs)
            elif action == "list_user_tasks":
                return await self._list_user_tasks(**kwargs)
            elif action == "get_overdue_tasks":
                return await self._get_overdue_tasks(**kwargs)
            elif action == "get_upcoming_tasks":
                return await self._get_upcoming_tasks(**kwargs)
            elif action == "search_tasks":
                return await self._search_tasks(**kwargs)
            else:
                return {"error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error in task management tool: {e}")
            return {"error": f"Task management error: {str(e)}"}
    
    async def _create_task(self, **kwargs) -> Dict[str, Any]:
        """Create a new task"""
        try:
            user_id = kwargs["user_id"]
            title = kwargs.get("title")
            
            if not title:
                return {"error": "Title is required for creating a task"}
                
            # Parse parameters
            description = kwargs.get("description", "")
            category = kwargs.get("category", "General")
            channel_id = kwargs.get("channel_id")
            timezone = kwargs.get("timezone", "UTC")
            
            # Parse priority
            priority_str = kwargs.get("priority", "NORMAL")
            try:
                priority = TaskPriorityLevel[priority_str]
            except KeyError:
                priority = TaskPriorityLevel.NORMAL
                
            # Parse due date
            due_date = None
            due_date_str = kwargs.get("due_date")
            if due_date_str:
                due_date = self._parse_due_date(due_date_str, timezone)
                
            # Create task object
            task = Task(
                title=title,
                description=description,
                due_date=due_date,
                priority=priority,
                category=category,
                created_by=user_id,
                channel_id=channel_id,
                timezone=timezone
            )
            
            # Create task in database
            task_id = await self.task_manager.create_task(task)
            
            # Get the created task to return full details
            created_task = await self.task_manager.get_task(task_id)
            
            return {
                "success": True,
                "message": f"Task '{title}' created successfully",
                "task_id": task_id,
                "task": self._task_to_dict(created_task) if created_task else None
            }
            
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return {"error": f"Failed to create task: {str(e)}"}
    
    async def _get_task(self, **kwargs) -> Dict[str, Any]:
        """Get a specific task by ID"""
        try:
            task_id = kwargs.get("task_id")
            if not task_id:
                return {"error": "Task ID is required"}
                
            task = await self.task_manager.get_task(task_id)
            if not task:
                return {"error": f"Task with ID {task_id} not found"}
                
            return {
                "success": True,
                "task": self._task_to_dict(task)
            }
            
        except Exception as e:
            logger.error(f"Error getting task: {e}")
            return {"error": f"Failed to get task: {str(e)}"}
    
    async def _update_task(self, **kwargs) -> Dict[str, Any]:
        """Update an existing task"""
        try:
            task_id = kwargs.get("task_id")
            if not task_id:
                return {"error": "Task ID is required"}
                
            # Get existing task
            task = await self.task_manager.get_task(task_id)
            if not task:
                return {"error": f"Task with ID {task_id} not found"}
                
            # Update fields if provided
            if "title" in kwargs:
                task.title = kwargs["title"]
            if "description" in kwargs:
                task.description = kwargs["description"]
            if "category" in kwargs:
                task.category = kwargs["category"]
            if "priority" in kwargs:
                try:
                    task.priority = TaskPriorityLevel[kwargs["priority"]]
                except KeyError:
                    pass  # Keep existing priority if invalid
            if "status" in kwargs:
                try:
                    task.status = TaskStatus[kwargs["status"]]
                except KeyError:
                    pass  # Keep existing status if invalid
            if "due_date" in kwargs:
                due_date_str = kwargs["due_date"]
                if due_date_str:
                    task.due_date = self._parse_due_date(due_date_str, task.timezone)
                else:
                    task.due_date = None
                    
            # Update task in database
            success = await self.task_manager.update_task(task)
            
            if success:
                return {
                    "success": True,
                    "message": f"Task {task_id} updated successfully",
                    "task": self._task_to_dict(task)
                }
            else:
                return {"error": "Failed to update task"}
                
        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return {"error": f"Failed to update task: {str(e)}"}
    
    async def _delete_task(self, **kwargs) -> Dict[str, Any]:
        """Delete a task"""
        try:
            task_id = kwargs.get("task_id")
            if not task_id:
                return {"error": "Task ID is required"}
                
            # Get task first to return info
            task = await self.task_manager.get_task(task_id)
            if not task:
                return {"error": f"Task with ID {task_id} not found"}
                
            success = await self.task_manager.delete_task(task_id)
            
            if success:
                return {
                    "success": True,
                    "message": f"Task '{task.title}' deleted successfully"
                }
            else:
                return {"error": "Failed to delete task"}
                
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return {"error": f"Failed to delete task: {str(e)}"}
    
    async def _complete_task(self, **kwargs) -> Dict[str, Any]:
        """Mark a task as completed"""
        try:
            task_id = kwargs.get("task_id")
            user_id = kwargs["user_id"]
            
            if not task_id:
                return {"error": "Task ID is required"}
                
            # Get task first
            task = await self.task_manager.get_task(task_id)
            if not task:
                return {"error": f"Task with ID {task_id} not found"}
                
            success = await self.task_manager.complete_task(task_id, user_id)
            
            if success:
                return {
                    "success": True,
                    "message": f"Task '{task.title}' completed successfully",
                    "was_recurring": task.recurrence_type != RecurrenceType.NONE
                }
            else:
                return {"error": "Failed to complete task or no permission"}
                
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            return {"error": f"Failed to complete task: {str(e)}"}
    
    async def _list_user_tasks(self, **kwargs) -> Dict[str, Any]:
        """List tasks for a user"""
        try:
            user_id = kwargs["user_id"]
            limit = kwargs.get("limit", 10)
            status_str = kwargs.get("status")
            
            # Parse status filter
            status_filter = None
            if status_str:
                try:
                    status_filter = TaskStatus[status_str]
                except KeyError:
                    return {"error": f"Invalid status: {status_str}"}
                    
            tasks = await self.task_manager.get_user_tasks(
                user_id, 
                status=status_filter,
                limit=limit
            )
            
            return {
                "success": True,
                "count": len(tasks),
                "tasks": [self._task_to_dict(task) for task in tasks]
            }
            
        except Exception as e:
            logger.error(f"Error listing user tasks: {e}")
            return {"error": f"Failed to list tasks: {str(e)}"}
    
    async def _get_overdue_tasks(self, **kwargs) -> Dict[str, Any]:
        """Get overdue tasks for a user"""
        try:
            user_id = kwargs["user_id"]
            limit = kwargs.get("limit", 10)
            
            # Get all user tasks and filter overdue
            all_tasks = await self.task_manager.get_user_tasks(user_id, limit=100)
            current_time = time.time()
            
            overdue_tasks = [
                task for task in all_tasks
                if (task.due_date and task.due_date < current_time and 
                    task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
            ][:limit]
            
            return {
                "success": True,
                "count": len(overdue_tasks),
                "tasks": [self._task_to_dict(task) for task in overdue_tasks]
            }
            
        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            return {"error": f"Failed to get overdue tasks: {str(e)}"}
    
    async def _get_upcoming_tasks(self, **kwargs) -> Dict[str, Any]:
        """Get upcoming tasks for a user"""
        try:
            user_id = kwargs["user_id"]
            hours_ahead = kwargs.get("hours_ahead", 24)
            limit = kwargs.get("limit", 10)
            
            # Get upcoming tasks
            current_time = time.time()
            future_time = current_time + (hours_ahead * 3600)
            
            all_tasks = await self.task_manager.get_user_tasks(user_id, limit=100)
            upcoming_tasks = [
                task for task in all_tasks
                if (task.due_date and 
                    current_time <= task.due_date <= future_time and
                    task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
            ][:limit]
            
            # Sort by due date
            upcoming_tasks.sort(key=lambda t: t.due_date or 0)
            
            return {
                "success": True,
                "count": len(upcoming_tasks),
                "hours_ahead": hours_ahead,
                "tasks": [self._task_to_dict(task) for task in upcoming_tasks]
            }
            
        except Exception as e:
            logger.error(f"Error getting upcoming tasks: {e}")
            return {"error": f"Failed to get upcoming tasks: {str(e)}"}
    
    async def _search_tasks(self, **kwargs) -> Dict[str, Any]:
        """Search tasks by title and description"""
        try:
            user_id = kwargs["user_id"]
            search_query = kwargs.get("search_query", "").lower()
            limit = kwargs.get("limit", 10)
            
            if not search_query:
                return {"error": "Search query is required"}
                
            # Get all user tasks and filter by search query
            all_tasks = await self.task_manager.get_user_tasks(user_id, limit=100)
            
            matching_tasks = []
            for task in all_tasks:
                if (search_query in task.title.lower() or 
                    search_query in (task.description or "").lower() or
                    search_query in task.category.lower()):
                    matching_tasks.append(task)
                    
                if len(matching_tasks) >= limit:
                    break
                    
            return {
                "success": True,
                "query": search_query,
                "count": len(matching_tasks),
                "tasks": [self._task_to_dict(task) for task in matching_tasks]
            }
            
        except Exception as e:
            logger.error(f"Error searching tasks: {e}")
            return {"error": f"Failed to search tasks: {str(e)}"}
    
    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """Convert Task object to dictionary for JSON serialization"""
        task_dict = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.name,
            "category": task.category,
            "created_by": task.created_by,
            "channel_id": task.channel_id,
            "timezone": task.timezone,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "recurrence_type": task.recurrence_type.value,
            "recurrence_interval": task.recurrence_interval
        }
        
        # Add optional fields
        if task.due_date:
            task_dict["due_date"] = task.due_date
            # Add human-readable due date
            try:
                tz = pytz.timezone(task.timezone)
                due_dt = datetime.fromtimestamp(task.due_date, tz)
                task_dict["due_date_formatted"] = due_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
            except:
                task_dict["due_date_formatted"] = "Invalid date"
                
        if task.completed_at:
            task_dict["completed_at"] = task.completed_at
            task_dict["completed_by"] = task.completed_by
            
        if task.parent_task_id:
            task_dict["parent_task_id"] = task.parent_task_id
            
        # Add computed fields
        if task.due_date:
            current_time = time.time()
            if task.due_date < current_time:
                overdue_seconds = current_time - task.due_date
                if overdue_seconds > 86400:  # More than 1 day
                    task_dict["overdue_days"] = int(overdue_seconds // 86400)
                else:
                    task_dict["overdue_hours"] = int(overdue_seconds // 3600)
            else:
                time_until_due = task.due_date - current_time
                if time_until_due > 86400:  # More than 1 day
                    task_dict["due_in_days"] = int(time_until_due // 86400)
                else:
                    task_dict["due_in_hours"] = int(time_until_due // 3600)
                    
        return task_dict
    
    def _parse_due_date(self, date_str: str, timezone: str = "UTC") -> Optional[float]:
        """Parse natural language or ISO date string into timestamp"""
        if not date_str:
            return None
            
        # This is a simplified parser - could be enhanced with more sophisticated NLP
        date_str = date_str.lower().strip()
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        try:
            # Try to parse as ISO format first
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = tz.localize(dt)
                return dt.timestamp()
            except ValueError:
                pass
                
            # Handle simple natural language cases
            if "tomorrow" in date_str:
                target = now + timedelta(days=1)
                target = target.replace(hour=9, minute=0, second=0, microsecond=0)  # Default 9 AM
            elif "today" in date_str:
                target = now.replace(hour=17, minute=0, second=0, microsecond=0)  # Default 5 PM
            elif "next week" in date_str:
                target = now + timedelta(weeks=1)
                target = target.replace(hour=9, minute=0, second=0, microsecond=0)
            elif "in" in date_str and ("hour" in date_str or "day" in date_str):
                # Parse "in X hours" or "in X days"
                parts = date_str.split()
                try:
                    num = int(parts[1])
                    if "hour" in date_str:
                        target = now + timedelta(hours=num)
                    elif "day" in date_str:
                        target = now + timedelta(days=num)
                        target = target.replace(hour=9, minute=0, second=0, microsecond=0)
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                # Default to tomorrow 9 AM if we can't parse
                target = now + timedelta(days=1)
                target = target.replace(hour=9, minute=0, second=0, microsecond=0)
                
            # Make sure the date is in the future
            if target <= now:
                target = now + timedelta(hours=1)
                
            return target.timestamp()
            
        except Exception as e:
            logger.error(f"Error parsing due date '{date_str}': {e}")
            return None