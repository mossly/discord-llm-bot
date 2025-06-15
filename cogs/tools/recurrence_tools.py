import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pytz

from .base_tool import BaseTool
from utils.task_manager import TaskManager, Task, RecurrenceType

logger = logging.getLogger(__name__)

class WeekdayRecurrenceTool(BaseTool):
    """Tool for creating weekday-only recurring tasks (Monday-Friday)"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "weekday_recurrence"
        self._description = "Create tasks that recur only on weekdays (Monday-Friday), skipping weekends"
        
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
                "user_id": {"type": "integer", "description": "Discord user ID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description (optional)"},
                "start_date": {"type": "string", "description": "Start date in ISO format"},
                "time_of_day": {"type": "string", "description": "Time of day (e.g., '9:00 AM')"},
                "end_date": {"type": "string", "description": "End date for recurrence (optional)"},
                "timezone": {"type": "string", "description": "User timezone (default: UTC)"},
                "category": {"type": "string", "description": "Task category"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"]}
            },
            "required": ["user_id", "title", "start_date"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a weekday-recurring task"""
        try:
            # Create task with weekday recurrence
            task = Task(
                title=kwargs["title"],
                description=kwargs.get("description", ""),
                created_by=kwargs["user_id"],
                category=kwargs.get("category", "General"),
                timezone=kwargs.get("timezone", "UTC"),
                recurrence_type=RecurrenceType.WEEKDAYS,
                recurrence_days_of_week=json.dumps([0, 1, 2, 3, 4]),  # Mon-Fri
                due_date=self._parse_start_date_time(kwargs["start_date"], kwargs.get("time_of_day"), kwargs.get("timezone", "UTC")),
                recurrence_end_date=self._parse_date(kwargs.get("end_date"), kwargs.get("timezone", "UTC")) if kwargs.get("end_date") else None
            )
            
            task_id = await self.task_manager.create_task(task)
            
            return {
                "success": True,
                "message": f"Weekday recurring task '{kwargs['title']}' created (Monday-Friday)",
                "task_id": task_id,
                "pattern": "Every weekday (Mon-Fri)"
            }
            
        except Exception as e:
            logger.error(f"Error creating weekday recurrence: {e}")
            return {"error": f"Failed to create weekday recurring task: {str(e)}"}
    
    def _parse_start_date_time(self, date_str: str, time_str: Optional[str], timezone: str) -> float:
        """Parse start date and time into timestamp"""
        # Implementation for parsing date/time combinations
        return datetime.now().timestamp()  # Placeholder
    
    def _parse_date(self, date_str: str, timezone: str) -> float:
        """Parse date string into timestamp"""
        return datetime.now().timestamp()  # Placeholder

class SpecificDaysRecurrenceTool(BaseTool):
    """Tool for creating tasks that recur on specific days of the week"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "specific_days_recurrence"
        self._description = "Create tasks that recur on specific days of the week (e.g., Monday, Wednesday, Friday)"
        
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
                "user_id": {"type": "integer", "description": "Discord user ID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description (optional)"},
                "days_of_week": {
                    "type": "array", 
                    "items": {"type": "string", "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
                    "description": "Days of week for recurrence"
                },
                "start_date": {"type": "string", "description": "Start date in ISO format"},
                "time_of_day": {"type": "string", "description": "Time of day (e.g., '9:00 AM')"},
                "end_date": {"type": "string", "description": "End date for recurrence (optional)"},
                "timezone": {"type": "string", "description": "User timezone (default: UTC)"},
                "category": {"type": "string", "description": "Task category"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"]}
            },
            "required": ["user_id", "title", "days_of_week", "start_date"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a specific-days recurring task"""
        try:
            # Convert day names to numbers (0=Monday, 6=Sunday)
            day_mapping = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }
            
            day_numbers = [day_mapping[day.lower()] for day in kwargs["days_of_week"]]
            
            task = Task(
                title=kwargs["title"],
                description=kwargs.get("description", ""),
                created_by=kwargs["user_id"],
                category=kwargs.get("category", "General"),
                timezone=kwargs.get("timezone", "UTC"),
                recurrence_type=RecurrenceType.SPECIFIC_DAYS,
                recurrence_days_of_week=json.dumps(sorted(day_numbers)),
                due_date=self._parse_start_date_time(kwargs["start_date"], kwargs.get("time_of_day"), kwargs.get("timezone", "UTC")),
                recurrence_end_date=self._parse_date(kwargs.get("end_date"), kwargs.get("timezone", "UTC")) if kwargs.get("end_date") else None
            )
            
            task_id = await self.task_manager.create_task(task)
            
            day_names = ", ".join(kwargs["days_of_week"])
            return {
                "success": True,
                "message": f"Recurring task '{kwargs['title']}' created for {day_names}",
                "task_id": task_id,
                "pattern": f"Every {day_names}"
            }
            
        except Exception as e:
            logger.error(f"Error creating specific days recurrence: {e}")
            return {"error": f"Failed to create specific days recurring task: {str(e)}"}
    
    def _parse_start_date_time(self, date_str: str, time_str: Optional[str], timezone: str) -> float:
        """Parse start date and time into timestamp"""
        return datetime.now().timestamp()  # Placeholder
    
    def _parse_date(self, date_str: str, timezone: str) -> float:
        """Parse date string into timestamp"""
        return datetime.now().timestamp()  # Placeholder

class MonthlyPositionRecurrenceTool(BaseTool):
    """Tool for creating tasks that recur on specific positions in the month (e.g., first Monday, last Friday)"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "monthly_position_recurrence"
        self._description = "Create tasks that recur on specific positions in the month (e.g., 'first Monday', 'last Friday', 'second Tuesday')"
        
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
                "user_id": {"type": "integer", "description": "Discord user ID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description (optional)"},
                "position": {
                    "type": "string", 
                    "enum": ["first", "second", "third", "fourth", "last"],
                    "description": "Position in the month"
                },
                "day_of_week": {
                    "type": "string",
                    "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                    "description": "Day of the week"
                },
                "time_of_day": {"type": "string", "description": "Time of day (e.g., '9:00 AM')"},
                "months_interval": {"type": "integer", "description": "Every N months (default: 1)"},
                "end_date": {"type": "string", "description": "End date for recurrence (optional)"},
                "timezone": {"type": "string", "description": "User timezone (default: UTC)"},
                "category": {"type": "string", "description": "Task category"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"]}
            },
            "required": ["user_id", "title", "position", "day_of_week"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a monthly position recurring task"""
        try:
            # Convert position to number (1-4 for first-fourth, -1 for last)
            position_mapping = {
                "first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1
            }
            
            # Convert day name to number
            day_mapping = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }
            
            position_num = position_mapping[kwargs["position"]]
            day_num = day_mapping[kwargs["day_of_week"].lower()]
            
            task = Task(
                title=kwargs["title"],
                description=kwargs.get("description", ""),
                created_by=kwargs["user_id"],
                category=kwargs.get("category", "General"),
                timezone=kwargs.get("timezone", "UTC"),
                recurrence_type=RecurrenceType.MONTHLY_POSITION,
                recurrence_week_of_month=position_num,
                recurrence_days_of_week=json.dumps([day_num]),
                recurrence_interval=kwargs.get("months_interval", 1),
                due_date=self._calculate_next_occurrence(position_num, day_num, kwargs.get("time_of_day"), kwargs.get("timezone", "UTC")),
                recurrence_end_date=self._parse_date(kwargs.get("end_date"), kwargs.get("timezone", "UTC")) if kwargs.get("end_date") else None
            )
            
            task_id = await self.task_manager.create_task(task)
            
            return {
                "success": True,
                "message": f"Monthly recurring task '{kwargs['title']}' created for {kwargs['position']} {kwargs['day_of_week']}",
                "task_id": task_id,
                "pattern": f"Every {kwargs['position']} {kwargs['day_of_week']} of the month"
            }
            
        except Exception as e:
            logger.error(f"Error creating monthly position recurrence: {e}")
            return {"error": f"Failed to create monthly position recurring task: {str(e)}"}
    
    def _calculate_next_occurrence(self, position: int, day_of_week: int, time_str: Optional[str], timezone: str) -> float:
        """Calculate the next occurrence of the position/day combination"""
        return datetime.now().timestamp()  # Placeholder
    
    def _parse_date(self, date_str: str, timezone: str) -> float:
        """Parse date string into timestamp"""
        return datetime.now().timestamp()  # Placeholder

class MultipleTimesPerPeriodTool(BaseTool):
    """Tool for creating tasks that occur multiple times per week/month"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "multiple_times_period_recurrence"
        self._description = "Create tasks that occur multiple times per week or month (e.g., '3 times per week', '2 times per month')"
        
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
                "user_id": {"type": "integer", "description": "Discord user ID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description (optional)"},
                "frequency": {"type": "integer", "description": "Number of times per period"},
                "period": {
                    "type": "string",
                    "enum": ["week", "month"],
                    "description": "Time period (week or month)"
                },
                "preferred_days": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred days of week (optional, for distribution)"
                },
                "start_date": {"type": "string", "description": "Start date in ISO format"},
                "end_date": {"type": "string", "description": "End date for recurrence (optional)"},
                "timezone": {"type": "string", "description": "User timezone (default: UTC)"},
                "category": {"type": "string", "description": "Task category"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"]}
            },
            "required": ["user_id", "title", "frequency", "period", "start_date"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create multiple occurrences per period"""
        try:
            period = kwargs["period"]
            frequency = kwargs["frequency"]
            
            if period == "week":
                recurrence_type = RecurrenceType.MULTIPLE_TIMES_WEEK
            else:  # month
                recurrence_type = RecurrenceType.MULTIPLE_TIMES_MONTH
            
            task = Task(
                title=kwargs["title"],
                description=kwargs.get("description", ""),
                created_by=kwargs["user_id"],
                category=kwargs.get("category", "General"),
                timezone=kwargs.get("timezone", "UTC"),
                recurrence_type=recurrence_type,
                recurrence_times_per_period=frequency,
                due_date=self._parse_date(kwargs["start_date"], kwargs.get("timezone", "UTC")),
                recurrence_end_date=self._parse_date(kwargs.get("end_date"), kwargs.get("timezone", "UTC")) if kwargs.get("end_date") else None,
                recurrence_custom_rule=json.dumps({
                    "preferred_days": kwargs.get("preferred_days", []),
                    "distribution": "even"  # Distribute evenly across period
                })
            )
            
            task_id = await self.task_manager.create_task(task)
            
            return {
                "success": True,
                "message": f"Recurring task '{kwargs['title']}' created {frequency} times per {period}",
                "task_id": task_id,
                "pattern": f"{frequency} times per {period}"
            }
            
        except Exception as e:
            logger.error(f"Error creating multiple times per period recurrence: {e}")
            return {"error": f"Failed to create multiple times per period task: {str(e)}"}
    
    def _parse_date(self, date_str: str, timezone: str) -> float:
        """Parse date string into timestamp"""
        return datetime.now().timestamp()  # Placeholder

class CustomIntervalRecurrenceTool(BaseTool):
    """Tool for creating tasks with custom day intervals"""
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
        self._name = "custom_interval_recurrence"
        self._description = "Create tasks that recur every N days (e.g., every 10 days, every 45 days)"
        
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
                "user_id": {"type": "integer", "description": "Discord user ID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description (optional)"},
                "interval_days": {"type": "integer", "description": "Number of days between occurrences"},
                "start_date": {"type": "string", "description": "Start date in ISO format"},
                "time_of_day": {"type": "string", "description": "Time of day (e.g., '9:00 AM')"},
                "skip_weekends": {"type": "boolean", "description": "Skip weekends when scheduling (default: false)"},
                "end_date": {"type": "string", "description": "End date for recurrence (optional)"},
                "timezone": {"type": "string", "description": "User timezone (default: UTC)"},
                "category": {"type": "string", "description": "Task category"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"]}
            },
            "required": ["user_id", "title", "interval_days", "start_date"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Create a custom interval recurring task"""
        try:
            task = Task(
                title=kwargs["title"],
                description=kwargs.get("description", ""),
                created_by=kwargs["user_id"],
                category=kwargs.get("category", "General"),
                timezone=kwargs.get("timezone", "UTC"),
                recurrence_type=RecurrenceType.CUSTOM_INTERVAL,
                recurrence_interval=kwargs["interval_days"],
                recurrence_skip_holidays=kwargs.get("skip_weekends", False),
                due_date=self._parse_start_date_time(kwargs["start_date"], kwargs.get("time_of_day"), kwargs.get("timezone", "UTC")),
                recurrence_end_date=self._parse_date(kwargs.get("end_date"), kwargs.get("timezone", "UTC")) if kwargs.get("end_date") else None
            )
            
            task_id = await self.task_manager.create_task(task)
            
            return {
                "success": True,
                "message": f"Recurring task '{kwargs['title']}' created every {kwargs['interval_days']} days",
                "task_id": task_id,
                "pattern": f"Every {kwargs['interval_days']} days"
            }
            
        except Exception as e:
            logger.error(f"Error creating custom interval recurrence: {e}")
            return {"error": f"Failed to create custom interval recurring task: {str(e)}"}
    
    def _parse_start_date_time(self, date_str: str, time_str: Optional[str], timezone: str) -> float:
        """Parse start date and time into timestamp"""
        return datetime.now().timestamp()  # Placeholder
    
    def _parse_date(self, date_str: str, timezone: str) -> float:
        """Parse date string into timestamp"""
        return datetime.now().timestamp()  # Placeholder