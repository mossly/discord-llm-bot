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
        
        # Defer tool registration to ensure ToolCalling cog is loaded
        asyncio.create_task(self._register_tools_when_ready())
        
        logger.info("Tasks cog loaded successfully")
        
    async def _register_tools_when_ready(self):
        """Register tools after a short delay to ensure all cogs are loaded"""
        await asyncio.sleep(0.5)  # Short delay to ensure all cogs are loaded
        
        tool_calling_cog = self.bot.get_cog("ToolCalling")
        if tool_calling_cog:
            tool_calling_cog.register_task_management_tool(self.task_manager, self.task_scheduler)
            logger.info("Successfully registered task management tool with ToolCalling cog")
        else:
            logger.error("ToolCalling cog not found after waiting - task management tools will not be available!")
        
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
            task_system_prompt = f"""You are a TASK MANAGER assistant. Your PRIMARY job is managing work tasks, but you can also create reminders FOR tasks when needed.

🎯 PRIMARY PURPOSE: TASK MANAGEMENT
- Check tasks: "what tasks do I have?" → task_management: list_user_tasks
- Create tasks: "create task to X" → task_management: create_task  
- Manage tasks: complete, update, delete → use task_management tool

🔔 SECONDARY PURPOSE: TASK-RELATED REMINDERS
- Custom alerts for tasks: "remind me at 8pm about the task" → manage_reminders
- NOT for general reminders: "remind me to call mom" (that's the /reminder command)

📋 CRYSTAL CLEAR TOOL USAGE:

**When user asks "what tasks do I have?":**
→ IMMEDIATELY call: task_management with action="list_user_tasks"
→ This shows their actual work tasks, NOT reminders

**When user wants to create a task:**
→ IMMEDIATELY call: task_management with action="create_task"
→ Tasks automatically get reminder notifications (24h, 6h, 1h before due)

**When user reports task completion (e.g., "I hung the laundry", "I did X", "I finished Y"):**
→ CRITICAL: Past tense = task completion! Look for these patterns:
   • "I hung/did/finished/completed/washed/cleaned..." = COMPLETION
   • "I've done..." / "I just..." = COMPLETION
→ IMMEDIATELY scan the Current Task Context for ANY matching pending task
→ If found: Use task_management with action="complete_task" and the task_id
→ Match broadly: "hung laundry" matches "hang the laundry", "did dishes" matches "wash dishes"
→ If no match: Acknowledge their work without creating a new task

**When user wants custom reminder times for a task:**
→ First: Create the task with task_management  
→ Then: Create custom reminders with manage_reminders
→ Example: "Task due midnight, remind at 8pm" = task + reminder

🛠️ AVAILABLE TOOLS:

**TASK TOOLS** (Your main job):
1. **task_management**: list_user_tasks, create_task, update_task, complete_task, delete_task, search_tasks
2. **weekday_recurrence**: Tasks repeating Monday-Friday only
3. **specific_days_recurrence**: Tasks on specific days (Mon, Wed, Fri)
4. **monthly_position_recurrence**: Tasks like "first Monday of month"
5. **multiple_times_period_recurrence**: Tasks "3 times per week"
6. **custom_interval_recurrence**: Tasks "every 10 days"

**REMINDER TOOL** (Only for task-related custom notifications):
7. **manage_reminders**: Create custom reminder notifications for tasks

⚡ IMMEDIATE ACTION TRIGGERS:
- "what tasks" / "my tasks" / "show tasks" → task_management: list_user_tasks
- "create task" / "add task" / "new task" → task_management: create_task
- "complete task" / "done with task" / "mark as complete" → task_management: complete_task
- "I did/hung/finished/completed X" → task_management: complete_task (IMPLICIT!)
- "remind me about task at [time]" → manage_reminders (after ensuring task exists)

🧠 IMPLICIT COMPLETION DETECTION:
When users use PAST TENSE without saying "complete", they're reporting completion!
- "I hung the laundry" = Find & complete "hang the laundry" task
- "I washed the dishes" = Find & complete "wash dishes" task  
- "Just finished the report" = Find & complete report-related task
ALWAYS check Current Task Context for matches when you see past tense!

📝 EXAMPLES:

✅ CORRECT USAGE:
- User: "What tasks do I have?" → Use task_management: list_user_tasks
- User: "Create task to review reports" → Use task_management: create_task
- User: "I hung the laundry out, mark as complete" → Use task_management: complete_task
- User: "I hung the laundry" → ALSO use task_management: complete_task (implicit!)
- User: "I finished the dishes" → Find "wash dishes" task and complete it
- User: "Just completed the report" → Find "review reports" task and complete it
- User: "Task due tomorrow, remind me at 8pm" → task_management + manage_reminders

❌ WRONG USAGE:
- User: "What tasks do I have?" → DON'T use manage_reminders (that's for notifications)
- User: "I did X, mark complete" → DON'T suggest /cancel reminder (search for task and complete it)
- User: "Remind me to call mom" → DON'T handle this (send to /reminder command)

🔄 AUTOMATIC TASK NOTIFICATIONS:
All tasks automatically get backup reminders at 24h, 6h, 1h before due date. You don't need to create these manually.

⚠️ IMPORTANT RULES:
- ALWAYS use tools immediately for task operations
- DON'T provide text-only responses for "what tasks do I have?"
- DO distinguish between task management and reminder creation
- DO execute actions directly without asking for confirmation

CURRENT USER CONTEXT:
User: {interaction.user.name} (ID: {interaction.user.id})
Channel: {interaction.channel.id}
{task_context}

Your job: Use task_management tools first for all task operations. Only use manage_reminders for custom task notification times.

🔍 IMPORTANT: You already have the user's current tasks listed above in "Current Task Context". When users mention completing a task, look for it in that context and use the task_id to complete it directly."""

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
                    "custom_interval_recurrence",
                    "manage_reminders"
                ],  # Task management tools + reminder tool for custom task notifications
                custom_system_prompt=task_system_prompt  # Pass the custom system prompt directly
            )
                
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