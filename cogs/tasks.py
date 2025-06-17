import discord
from discord.ext import commands
from discord import app_commands
import logging
import time
from typing import Optional, List
import pytz
from datetime import datetime, timedelta
import asyncio
import os

from utils.task_manager import (
    TaskManager, Task, TaskStatus, TaskPriorityLevel, ResponsibilityType, 
    RecurrenceType, TaskAssignment
)
from utils.background_task_manager import BackgroundTaskManager, TaskPriority as BGTaskPriority
from utils.task_scheduler import TaskScheduler
from utils.embed_utils import create_error_embed, create_success_embed, send_embed

logger = logging.getLogger(__name__)

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.background_task_manager = BackgroundTaskManager()
        self.task_manager = TaskManager(self.background_task_manager)
        self.task_scheduler = None  # Will be initialized in cog_load
        self._user_timezones = {}  # Cache for user timezones
        
    # Manual task command group removed - use /task natural language interface instead
        
    async def cog_load(self):
        """Initialize the task manager when the cog loads"""
        await self.background_task_manager.start()
        await self.task_manager.initialize()
        
        # Initialize task scheduler
        self.task_scheduler = TaskScheduler(self.bot, self.task_manager, self.background_task_manager)
        await self.task_scheduler.start()
        
        # Register task management tool with tool calling cog
        tool_calling_cog = self.bot.get_cog("ToolCalling")
        if tool_calling_cog:
            tool_calling_cog.register_task_management_tool(self.task_manager)
        
        logger.info("Tasks cog loaded successfully")
        
    async def cog_unload(self):
        """Cleanup when the cog unloads"""
        if self.task_scheduler:
            await self.task_scheduler.stop()
        await self.task_manager.cleanup()
        await self.background_task_manager.stop()
        logger.info("Tasks cog unloaded")
        
    def _parse_due_date(self, date_str: str, timezone: str = "UTC") -> Optional[float]:
        """Parse natural language due date into timestamp"""
        if not date_str:
            return None
            
        # This is a simplified parser - could be enhanced with more sophisticated NLP
        date_str = date_str.lower().strip()
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        try:
            # Handle simple cases
            if "tomorrow" in date_str:
                target = now + timedelta(days=1)
                # Try to extract time
                if "pm" in date_str or "am" in date_str:
                    time_part = date_str.split()[-1]
                    if "pm" in time_part:
                        hour = int(time_part.replace("pm", ""))
                        if hour != 12:
                            hour += 12
                    else:
                        hour = int(time_part.replace("am", ""))
                        if hour == 12:
                            hour = 0
                    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
                else:
                    target = target.replace(hour=9, minute=0, second=0, microsecond=0)  # Default 9 AM
                    
            elif "today" in date_str:
                target = now
                if "pm" in date_str or "am" in date_str:
                    time_part = date_str.split()[-1]
                    if "pm" in time_part:
                        hour = int(time_part.replace("pm", ""))
                        if hour != 12:
                            hour += 12
                    else:
                        hour = int(time_part.replace("am", ""))
                        if hour == 12:
                            hour = 0
                    target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
                    
            elif "in" in date_str and ("hour" in date_str or "day" in date_str):
                # Parse "in X hours" or "in X days"
                parts = date_str.split()
                try:
                    num = int(parts[1])
                    if "hour" in date_str:
                        target = now + timedelta(hours=num)
                    elif "day" in date_str:
                        target = now + timedelta(days=num)
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
            
    async def _get_user_timezone(self, user_id: int) -> str:
        """Get user's timezone, defaulting to UTC"""
        # Check cache first
        if user_id in self._user_timezones:
            return self._user_timezones[user_id]
            
        # For now, default to UTC - could be enhanced to check reminder system's timezone data
        timezone = "UTC"
        self._user_timezones[user_id] = timezone
        return timezone
    
    async def _get_task_context_for_user(self, user_id: int) -> str:
        """Generate task context for LLM system prompt"""
        try:
            # Get user's tasks
            all_tasks = await self.task_manager.get_user_tasks(user_id, limit=50)
            
            if not all_tasks:
                return "\nCurrent Task Context: User has no tasks."
            
            # Categorize tasks
            pending_tasks = [t for t in all_tasks if t.status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS]]
            overdue_tasks = []
            upcoming_tasks = []
            
            current_time = time.time()
            for task in pending_tasks:
                if task.due_date:
                    if task.due_date < current_time:
                        overdue_tasks.append(task)
                    elif task.due_date < current_time + (24 * 3600):  # Next 24 hours
                        upcoming_tasks.append(task)
            
            context_parts = ["\nCurrent Task Context:"]
            
            # Add overdue tasks (high priority)
            if overdue_tasks:
                context_parts.append(f"\n⚠️ OVERDUE TASKS ({len(overdue_tasks)}):")
                for task in overdue_tasks[:5]:  # Limit to 5 most important
                    hours_overdue = int((current_time - task.due_date) / 3600)
                    context_parts.append(f"  - ID {task.id}: '{task.title}' (overdue by {hours_overdue}h)")
            
            # Add upcoming tasks
            if upcoming_tasks:
                context_parts.append(f"\n📅 UPCOMING TASKS ({len(upcoming_tasks)}):")
                for task in upcoming_tasks[:5]:
                    hours_until = int((task.due_date - current_time) / 3600)
                    context_parts.append(f"  - ID {task.id}: '{task.title}' (due in {hours_until}h)")
            
            # Add other pending tasks
            other_pending = [t for t in pending_tasks if t not in overdue_tasks and t not in upcoming_tasks]
            if other_pending:
                context_parts.append(f"\n📝 OTHER PENDING TASKS ({len(other_pending)}):")
                for task in other_pending[:7]:  # Limit to 7
                    due_info = f" (due: {datetime.fromtimestamp(task.due_date).strftime('%m/%d')})" if task.due_date else ""
                    context_parts.append(f"  - ID {task.id}: '{task.title}'{due_info}")
            
            # Add completed recent tasks for reference
            completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
            if completed_tasks:
                recent_completed = [t for t in completed_tasks if t.completed_at and t.completed_at > current_time - (7 * 24 * 3600)]  # Last 7 days
                if recent_completed:
                    context_parts.append(f"\n✅ RECENTLY COMPLETED ({len(recent_completed)}):")
                    for task in recent_completed[:3]:
                        context_parts.append(f"  - '{task.title}' (completed {int((current_time - task.completed_at) / 86400)}d ago)")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error generating task context for user {user_id}: {e}")
            return "\nCurrent Task Context: Error loading tasks."
    
    @app_commands.command(name="task", description="Natural language task management with AI assistant")
    @app_commands.describe(
        prompt="Your task-related request or question",
        model="AI model to use (optional)"
    )
    async def task_chat(
        self, 
        interaction: discord.Interaction, 
        prompt: str,
        model: Optional[str] = None
    ):
        """Task-focused AI chat interface"""
        await interaction.response.defer(thinking=True)
        
        try:
            # Generate task context for this user
            task_context = await self._get_task_context_for_user(interaction.user.id)
            
            # Create task-specific system prompt
            task_system_prompt = f"""You are a personal task management assistant with powerful recurrence capabilities. You help users manage WORK TASKS and PROJECT TRACKING through natural language conversation.

WHAT TASKS ARE FOR:
- Work items that need tracking: "Create presentation for client meeting"
- Projects with due dates and priorities: "Finish quarterly report by Friday"
- Recurring work patterns: "Review weekly metrics every Monday"
- Items that need status updates and completion tracking
- Complex workflows with assignments and collaboration

WHAT TASKS ARE NOT FOR:
- Simple time-based notifications: "Remind me to call mom"
- One-time personal alerts that don't need tracking
- Basic reminders without status or completion tracking

ENHANCED TIME PARSING:
The system now supports advanced time expressions for due dates:
- "6pm tonight", "tonight at 6pm", "midnight tonight"  
- "3pm today", "today at 3pm"
- All previous patterns: "tomorrow at 3pm", "in 2 hours", "Friday morning"

AVAILABLE TOOLS:
1. **task_management**: Basic CRUD operations (create, read, update, delete, list, search, bulk operations)
2. **weekday_recurrence**: Creates tasks that repeat Monday-Friday only (skips weekends)
3. **specific_days_recurrence**: Creates tasks for specific days (e.g., "Mon, Wed, Fri" or "Tue, Thu")
4. **monthly_position_recurrence**: Creates tasks for positions in month (e.g., "first Monday", "last Friday", "second Tuesday")
5. **multiple_times_period_recurrence**: Creates tasks that occur multiple times per week/month (e.g., "3 times per week")
6. **custom_interval_recurrence**: Creates tasks with custom day intervals (e.g., "every 10 days", "every 45 days")

TOOL SELECTION GUIDELINES:
- For "weekday only" or "business days": Use **weekday_recurrence**
- For specific days like "Monday and Wednesday": Use **specific_days_recurrence**
- For "first Monday of month" or "last Friday": Use **monthly_position_recurrence**
- For "3 times per week" or "twice a month": Use **multiple_times_period_recurrence**
- For "every 10 days" or custom intervals: Use **custom_interval_recurrence**
- For simple daily/weekly/monthly: Use **task_management** with basic recurrence
- For one-time tasks or basic operations: Use **task_management**

NATURAL LANGUAGE EXAMPLES:
- "Water plants every weekday" → weekday_recurrence
- "Team meeting every Monday and Friday" → specific_days_recurrence  
- "Monthly report on the first Tuesday" → monthly_position_recurrence
- "Exercise 3 times per week" → multiple_times_period_recurrence
- "Check security every 15 days" → custom_interval_recurrence
- "Daily standup at 9am" → task_management (simple daily)

AUTOMATIC NOTIFICATIONS:
Tasks automatically create backup reminders for reliable notifications at:
- 24 hours before due date
- 6 hours before due date  
- 1 hour before due date
- When overdue
These reminders are managed automatically - you don't need to create them separately.

IMPORTANT GUIDELINES:
- Choose the MOST SPECIFIC tool for the user's request
- When users mention complex recurrence, use specialized tools to hide the complexity
- Always search for existing tasks first when users mention task names
- Be proactive about suggesting better organization patterns
- Ask clarifying questions when recurrence pattern is ambiguous
- Provide clear confirmation of the recurrence pattern created

CURRENT USER CONTEXT:
User: {interaction.user.name} (ID: {interaction.user.id})
Channel: {interaction.channel.id}
{task_context}

Remember: You have access to the user's current tasks above. When they reference tasks by name or description, match them to existing tasks when possible."""

            # Get AI commands cog to process the request
            ai_commands = self.bot.get_cog("AICommands")
            if not ai_commands:
                embed = discord.Embed(
                    title="❌ Error", 
                    description="AI commands system not available.", 
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create a custom system prompt by temporarily modifying the environment
            original_system_prompt = os.environ.get('SYSTEM_PROMPT', '')
            os.environ['SYSTEM_PROMPT'] = task_system_prompt
            
            try:
                # Process through AI with restricted tools (only task management)
                username = interaction.user.name
                formatted_prompt = f"{username}: {prompt}"
                
                # Use the AI processing with task management focus and restricted tools
                await ai_commands._process_ai_request(
                    formatted_prompt, 
                    model or "gemini-2.5-flash-preview",  # Default model
                    interaction=interaction, 
                    attachments=[], 
                    fun=False, 
                    web_search=False, 
                    deep_research=False, 
                    tool_calling=True,  # Enable tools for task management
                    max_tokens=4000,
                    allowed_tools=[
                        "task_management", 
                        "weekday_recurrence", 
                        "specific_days_recurrence", 
                        "monthly_position_recurrence", 
                        "multiple_times_period_recurrence", 
                        "custom_interval_recurrence"
                    ]  # Restrict to only task management tools
                )
            finally:
                # Restore original system prompt
                os.environ['SYSTEM_PROMPT'] = original_system_prompt
                
        except Exception as e:
            logger.error(f"Error in task chat: {e}")
            embed = discord.Embed(
                title="❌ Error", 
                description="An error occurred while processing your task request.", 
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
        
    # Manual task commands removed - use /task natural language interface instead
    # 
    # Example usage:
    # /task create a task to clean the kitchen due tomorrow
    # /task show me my overdue tasks
    # /task mark the grocery shopping task as complete
    # /task what do I need to do today?

async def setup(bot):
    await bot.add_cog(Tasks(bot))