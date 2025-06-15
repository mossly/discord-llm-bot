import discord
from discord.ext import commands
from discord import app_commands
import logging
import time
from typing import Optional, List
import pytz
from datetime import datetime, timedelta
import asyncio

from utils.task_manager import (
    TaskManager, Task, TaskStatus, TaskPriorityLevel, ResponsibilityType, 
    RecurrenceType, TaskAssignment
)
from utils.background_task_manager import BackgroundTaskManager, TaskPriority as BGTaskPriority
from utils.task_scheduler import TaskScheduler
from utils.embed_utils import create_error_embed, create_success_embed, send_embed

logger = logging.getLogger(__name__)

class TaskModal(discord.ui.Modal, title='Create New Task'):
    def __init__(self, user_timezone: str = "UTC"):
        super().__init__()
        self.user_timezone = user_timezone
        
    title_input = discord.ui.TextInput(
        label='Task Title',
        placeholder='Enter a short, descriptive title for your task...',
        max_length=100,
        required=True
    )
    
    description_input = discord.ui.TextInput(
        label='Description (Optional)',
        placeholder='Add more details about this task...',
        style=discord.TextStyle.long,
        max_length=1000,
        required=False
    )
    
    due_date_input = discord.ui.TextInput(
        label='Due Date (Optional)',
        placeholder='e.g., "tomorrow 3pm", "Friday at 9am", "in 2 days"',
        max_length=50,
        required=False
    )
    
    category_input = discord.ui.TextInput(
        label='Category (Optional)',
        placeholder='e.g., Work, Personal, Study',
        max_length=30,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # This will be handled by the cog
        pass

class TaskPrioritySelect(discord.ui.Select):
    def __init__(self, default_priority: str = "normal"):
        options = [
            discord.SelectOption(
                label="Low Priority",
                description="Not urgent, can wait",
                value="low",
                emoji="🟢",
                default=(default_priority == "low")
            ),
            discord.SelectOption(
                label="Normal Priority", 
                description="Standard priority task",
                value="normal",
                emoji="🟡",
                default=(default_priority == "normal")
            ),
            discord.SelectOption(
                label="High Priority",
                description="Important, should be done soon", 
                value="high",
                emoji="🟠",
                default=(default_priority == "high")
            ),
            discord.SelectOption(
                label="Critical Priority",
                description="Urgent, needs immediate attention",
                value="critical",
                emoji="🔴",
                default=(default_priority == "critical")
            )
        ]
        super().__init__(placeholder="Select task priority...", options=options)
        self.selected_priority = default_priority
        
    async def callback(self, interaction: discord.Interaction):
        self.selected_priority = self.values[0]
        await interaction.response.defer()

class TaskEditModal(discord.ui.Modal, title='Edit Task'):
    def __init__(self, task: Task, user_timezone: str = "UTC"):
        super().__init__()
        self.task = task
        self.user_timezone = user_timezone
        
        # Pre-fill with existing values
        self.title_input.default = task.title
        self.description_input.default = task.description or ""
        self.category_input.default = task.category
        
        # Format due date for display
        if task.due_date:
            try:
                tz = pytz.timezone(user_timezone)
                due_dt = datetime.fromtimestamp(task.due_date, tz)
                self.due_date_input.default = due_dt.strftime("%m/%d/%Y %I:%M %p")
            except:
                self.due_date_input.default = ""
        
    title_input = discord.ui.TextInput(
        label='Task Title',
        placeholder='Enter a short, descriptive title for your task...',
        max_length=100,
        required=True
    )
    
    description_input = discord.ui.TextInput(
        label='Description (Optional)',
        placeholder='Add more details about this task...',
        style=discord.TextStyle.long,
        max_length=1000,
        required=False
    )
    
    due_date_input = discord.ui.TextInput(
        label='Due Date (Optional)',
        placeholder='e.g., "tomorrow 3pm", "Friday at 9am", "MM/DD/YYYY HH:MM AM/PM"',
        max_length=50,
        required=False
    )
    
    category_input = discord.ui.TextInput(
        label='Category (Optional)',
        placeholder='e.g., Work, Personal, Study',
        max_length=30,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # This will be handled by the cog
        pass

class TaskStatusSelect(discord.ui.Select):
    def __init__(self, current_status: TaskStatus = TaskStatus.TODO):
        options = [
            discord.SelectOption(
                label="To Do",
                description="Task is pending",
                value="TODO",
                emoji="📝",
                default=(current_status == TaskStatus.TODO)
            ),
            discord.SelectOption(
                label="In Progress",
                description="Currently working on this task",
                value="IN_PROGRESS",
                emoji="⏳",
                default=(current_status == TaskStatus.IN_PROGRESS)
            ),
            discord.SelectOption(
                label="Completed",
                description="Task is finished",
                value="COMPLETED",
                emoji="✅",
                default=(current_status == TaskStatus.COMPLETED)
            ),
            discord.SelectOption(
                label="Cancelled",
                description="Task is no longer needed",
                value="CANCELLED",
                emoji="❌",
                default=(current_status == TaskStatus.CANCELLED)
            )
        ]
        super().__init__(placeholder="Select task status...", options=options)
        self.selected_status = current_status.value
        
    async def callback(self, interaction: discord.Interaction):
        self.selected_status = self.values[0]
        await interaction.response.defer()

class TaskActionView(discord.ui.View):
    def __init__(self, task: Task, user_id: int, task_manager, task_scheduler):
        super().__init__(timeout=300)
        self.task = task
        self.user_id = user_id
        self.task_manager = task_manager
        self.task_scheduler = task_scheduler
        
        # Only show complete button if task is not already completed
        if task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
            self.add_item(self.complete_button)
        
        # Only allow editing if user is the creator
        if task.created_by == user_id:
            self.add_item(self.edit_button)
            self.add_item(self.delete_button)
    
    @discord.ui.button(label="Complete", style=discord.ButtonStyle.green, emoji="✅")
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only interact with your own tasks.", ephemeral=True)
            return
            
        try:
            success = await self.task_manager.complete_task(self.task.id, interaction.user.id)
            
            if success:
                embed = create_success_embed(
                    f"Task **{self.task.title}** marked as completed! 🎉",
                    "✅ Task Completed"
                )
                
                # Check if it was a recurring task
                if self.task.recurrence_type != RecurrenceType.NONE:
                    embed.add_field(
                        name="🔄 Recurring Task",
                        value="A new occurrence has been created for the next due date.",
                        inline=False
                    )
            else:
                embed = create_error_embed("Failed to complete task. You may not have permission.")
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error completing task {self.task.id}: {e}")
            embed = create_error_embed("An error occurred while completing the task.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Edit", style=discord.ButtonStyle.blurple, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only edit your own tasks.", ephemeral=True)
            return
            
        # This will be handled by showing the edit modal
        await interaction.response.send_message("Edit functionality coming soon!", ephemeral=True)
    
    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only delete your own tasks.", ephemeral=True)
            return
            
        # Show confirmation
        confirm_view = TaskDeleteConfirmView(self.task, self.user_id, self.task_manager)
        embed = discord.Embed(
            title="⚠️ Confirm Deletion",
            description=f"Are you sure you want to delete the task **{self.task.title}**?\n\nThis action cannot be undone.",
            color=0xff6b35
        )
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

class TaskDeleteConfirmView(discord.ui.View):
    def __init__(self, task: Task, user_id: int, task_manager):
        super().__init__(timeout=60)
        self.task = task
        self.user_id = user_id
        self.task_manager = task_manager
    
    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.red, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only delete your own tasks.", ephemeral=True)
            return
            
        try:
            success = await self.task_manager.delete_task(self.task.id)
            
            if success:
                embed = create_success_embed(
                    f"Task **{self.task.title}** has been deleted.",
                    "🗑️ Task Deleted"
                )
            else:
                embed = create_error_embed("Failed to delete task.")
                
            await interaction.response.edit_message(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Error deleting task {self.task.id}: {e}")
            embed = create_error_embed("An error occurred while deleting the task.")
            await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your task.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="✅ Deletion Cancelled",
            description="The task was not deleted.",
            color=0x32a956
        )
        await interaction.response.edit_message(embed=embed, view=None)

class BulkTaskActionView(discord.ui.View):
    def __init__(self, tasks: List[Task], user_id: int, task_manager):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.user_id = user_id
        self.task_manager = task_manager
        self.selected_tasks = set()
        
        # Create task selection dropdown
        self.task_select = BulkTaskSelect(tasks[:25])  # Discord limit
        self.add_item(self.task_select)
    
    @discord.ui.button(label="Complete Selected", style=discord.ButtonStyle.green, emoji="✅")
    async def complete_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only modify your own tasks.", ephemeral=True)
            return
            
        if not self.task_select.selected_task_ids:
            await interaction.response.send_message("Please select tasks first.", ephemeral=True)
            return
            
        completed_count = 0
        for task_id in self.task_select.selected_task_ids:
            try:
                success = await self.task_manager.complete_task(task_id, interaction.user.id)
                if success:
                    completed_count += 1
            except Exception as e:
                logger.error(f"Error completing task {task_id}: {e}")
                
        embed = create_success_embed(
            f"Completed {completed_count} out of {len(self.task_select.selected_task_ids)} selected tasks.",
            "✅ Bulk Complete"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BulkTaskSelect(discord.ui.Select):
    def __init__(self, tasks: List[Task]):
        options = []
        for task in tasks:
            # Status emoji
            status_emoji = {
                TaskStatus.TODO: "📝",
                TaskStatus.IN_PROGRESS: "⏳", 
                TaskStatus.COMPLETED: "✅",
                TaskStatus.OVERDUE: "⚠️",
                TaskStatus.CANCELLED: "❌"
            }.get(task.status, "📝")
            
            # Truncate title for display
            display_title = task.title[:50] + "..." if len(task.title) > 50 else task.title
            
            options.append(discord.SelectOption(
                label=display_title,
                description=f"{status_emoji} {task.category}",
                value=str(task.id)
            ))
        
        super().__init__(
            placeholder="Select tasks for bulk operations...",
            options=options,
            max_values=min(len(options), 25)
        )
        self.selected_task_ids = set()
        
    async def callback(self, interaction: discord.Interaction):
        self.selected_task_ids = set(int(task_id) for task_id in self.values)
        await interaction.response.send_message(
            f"Selected {len(self.selected_task_ids)} tasks.",
            ephemeral=True
        )

class TaskListView(discord.ui.View):
    def __init__(self, tasks: List[Task], user_id: int, page: int = 0):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.user_id = user_id
        self.page = page
        self.per_page = 5
        
        # Update button states
        self.update_buttons()
        
    def update_buttons(self):
        total_pages = max(1, (len(self.tasks) + self.per_page - 1) // self.per_page)
        
        # Update previous button
        self.previous_page.disabled = self.page <= 0
        
        # Update next button  
        self.next_page.disabled = self.page >= total_pages - 1
        
    def get_current_tasks(self) -> List[Task]:
        start = self.page * self.per_page
        end = start + self.per_page
        return self.tasks[start:end]
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only interact with your own task list.", ephemeral=True)
            return
            
        self.page = max(0, self.page - 1)
        self.update_buttons()
        
        embed = self.create_task_list_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only interact with your own task list.", ephemeral=True)
            return
            
        total_pages = max(1, (len(self.tasks) + self.per_page - 1) // self.per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self.update_buttons()
        
        embed = self.create_task_list_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can only interact with your own task list.", ephemeral=True)
            return
            
        # This will be handled by the cog to refresh the task list
        await interaction.response.send_message("Refreshing task list...", ephemeral=True)
        
    def create_task_list_embed(self) -> discord.Embed:
        current_tasks = self.get_current_tasks()
        total_pages = max(1, (len(self.tasks) + self.per_page - 1) // self.per_page)
        
        if not current_tasks:
            embed = discord.Embed(
                title="📋 Your Tasks",
                description="You don't have any tasks yet. Use `/task add` to create one!",
                color=0x3498db
            )
            return embed
            
        embed = discord.Embed(
            title="📋 Your Tasks",
            color=0x3498db
        )
        
        for i, task in enumerate(current_tasks):
            # Status emoji
            status_emoji = {
                TaskStatus.TODO: "📝",
                TaskStatus.IN_PROGRESS: "⏳", 
                TaskStatus.COMPLETED: "✅",
                TaskStatus.OVERDUE: "⚠️",
                TaskStatus.CANCELLED: "❌"
            }.get(task.status, "📝")
            
            # Priority emoji
            priority_emoji = {
                TaskPriorityLevel.LOW: "🟢",
                TaskPriorityLevel.NORMAL: "🟡",
                TaskPriorityLevel.HIGH: "🟠", 
                TaskPriorityLevel.CRITICAL: "🔴"
            }.get(task.priority, "🟡")
            
            # Due date info
            due_info = ""
            if task.due_date:
                try:
                    tz = pytz.timezone(task.timezone)
                    due_dt = datetime.fromtimestamp(task.due_date, tz)
                    now = datetime.now(tz)
                    
                    if due_dt < now:
                        time_diff = now - due_dt
                        if time_diff.days > 0:
                            due_info = f" (⚠️ {time_diff.days}d overdue)"
                        else:
                            hours = int(time_diff.total_seconds() // 3600)
                            due_info = f" (⚠️ {hours}h overdue)"
                    else:
                        due_info = f"\n📅 Due: {due_dt.strftime('%m/%d %I:%M %p')}"
                except:
                    due_info = ""
                    
            field_title = f"{status_emoji} {priority_emoji} {task.title}"
            field_value = f"**Category:** {task.category}{due_info}"
            if task.description:
                field_value += f"\n*{task.description[:100]}{'...' if len(task.description) > 100 else ''}*"
                
            embed.add_field(
                name=field_title,
                value=field_value,
                inline=False
            )
            
        embed.set_footer(text=f"Page {self.page + 1} of {total_pages} • {len(self.tasks)} total tasks")
        return embed

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.background_task_manager = BackgroundTaskManager()
        self.task_manager = TaskManager(self.background_task_manager)
        self.task_scheduler = None  # Will be initialized in cog_load
        self._user_timezones = {}  # Cache for user timezones
        
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
        
    @task.command(name="add", description="Create a new task")
    async def add_task(self, interaction: discord.Interaction):
        """Create a new task using a modal form"""
        user_timezone = await self._get_user_timezone(interaction.user.id)
        modal = TaskModal(user_timezone)
        
        async def modal_callback(modal_interaction: discord.Interaction):
            # Parse the input
            title = modal.title_input.value.strip()
            description = modal.description_input.value.strip() if modal.description_input.value else ""
            due_date_str = modal.due_date_input.value.strip() if modal.due_date_input.value else ""
            category = modal.category_input.value.strip() if modal.category_input.value else "General"
            
            # Parse due date
            due_date = self._parse_due_date(due_date_str, user_timezone) if due_date_str else None
            
            # Create task object
            task = Task(
                title=title,
                description=description,
                due_date=due_date,
                priority=TaskPriorityLevel.NORMAL,  # Default priority
                category=category,
                created_by=interaction.user.id,
                channel_id=interaction.channel.id,
                timezone=user_timezone
            )
            
            try:
                # Create the task
                task_id = await self.task_manager.create_task(task)
                
                # Create success embed
                embed = create_success_embed(
                    f"Task **{title}** created successfully!",
                    "✅ Task Created"
                )
                
                if due_date:
                    tz = pytz.timezone(user_timezone)
                    due_dt = datetime.fromtimestamp(due_date, tz)
                    embed.add_field(
                        name="📅 Due Date",
                        value=due_dt.strftime("%A, %B %d, %Y at %I:%M %p"),
                        inline=False
                    )
                    
                embed.add_field(name="📂 Category", value=category, inline=True)
                embed.add_field(name="🆔 Task ID", value=str(task_id), inline=True)
                
                await modal_interaction.response.send_message(embed=embed, ephemeral=True)
                
            except Exception as e:
                logger.error(f"Error creating task: {e}")
                embed = create_error_embed("Failed to create task. Please try again.")
                await modal_interaction.response.send_message(embed=embed, ephemeral=True)
                
        modal.on_submit = modal_callback
        await interaction.response.send_modal(modal)
        
    @task.command(name="list", description="View your tasks")
    @app_commands.describe(
        status="Filter tasks by status",
        category="Filter tasks by category"
    )
    async def list_tasks(
        self, 
        interaction: discord.Interaction,
        status: Optional[str] = None,
        category: Optional[str] = None
    ):
        """List user's tasks with optional filtering"""
        try:
            # Parse status filter
            status_filter = None
            if status:
                try:
                    status_filter = TaskStatus(status.upper())
                except ValueError:
                    embed = create_error_embed(f"Invalid status '{status}'. Valid options: TODO, IN_PROGRESS, COMPLETED, OVERDUE, CANCELLED")
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
            # Get user's tasks
            tasks = await self.task_manager.get_user_tasks(
                interaction.user.id,
                status=status_filter,
                limit=100  # Get more for local filtering
            )
            
            # Apply category filter if specified
            if category:
                tasks = [task for task in tasks if task.category.lower() == category.lower()]
                
            # Update overdue status
            current_time = time.time()
            for task in tasks:
                if (task.due_date and task.due_date < current_time and 
                    task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]):
                    task.status = TaskStatus.OVERDUE
                    await self.task_manager.update_task(task)
                    
            # Create and send the task list view
            if not tasks:
                filter_text = ""
                if status_filter:
                    filter_text += f" with status '{status_filter.value}'"
                if category:
                    filter_text += f" in category '{category}'"
                    
                embed = discord.Embed(
                    title="📋 Your Tasks",
                    description=f"No tasks found{filter_text}.",
                    color=0x3498db
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            view = TaskListView(tasks, interaction.user.id)
            embed = view.create_task_list_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error listing tasks: {e}")
            embed = create_error_embed("Failed to retrieve tasks. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @task.command(name="complete", description="Mark a task as completed")
    @app_commands.describe(task_id="The ID of the task to complete")
    async def complete_task(self, interaction: discord.Interaction, task_id: int):
        """Mark a task as completed"""
        try:
            # Check if task exists and user has permission
            task = await self.task_manager.get_task(task_id)
            if not task:
                embed = create_error_embed(f"Task with ID {task_id} not found.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Complete the task
            success = await self.task_manager.complete_task(task_id, interaction.user.id)
            
            if success:
                embed = create_success_embed(
                    f"Task **{task.title}** marked as completed! 🎉",
                    "✅ Task Completed"
                )
                
                # Add completion details
                tz = pytz.timezone(task.timezone)
                completed_at = datetime.now(tz)
                embed.add_field(
                    name="⏰ Completed At",
                    value=completed_at.strftime("%A, %B %d, %Y at %I:%M %p"),
                    inline=False
                )
                
                # Check if it was a recurring task
                if task.recurrence_type != RecurrenceType.NONE:
                    embed.add_field(
                        name="🔄 Recurring Task",
                        value="A new occurrence has been created for the next due date.",
                        inline=False
                    )
                    
            else:
                embed = create_error_embed(
                    "You don't have permission to complete this task, or it's already completed."
                )
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}")
            embed = create_error_embed("Failed to complete task. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @task.command(name="delete", description="Delete a task")
    @app_commands.describe(task_id="The ID of the task to delete")
    async def delete_task(self, interaction: discord.Interaction, task_id: int):
        """Delete a task"""
        try:
            # Check if task exists and user has permission
            task = await self.task_manager.get_task(task_id)
            if not task:
                embed = create_error_embed(f"Task with ID {task_id} not found.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Only the creator can delete the task
            if task.created_by != interaction.user.id:
                embed = create_error_embed("You can only delete tasks that you created.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Delete the task
            success = await self.task_manager.delete_task(task_id)
            
            if success:
                embed = create_success_embed(
                    f"Task **{task.title}** has been deleted.",
                    "🗑️ Task Deleted"
                )
            else:
                embed = create_error_embed("Failed to delete task.")
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            embed = create_error_embed("Failed to delete task. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @task.command(name="details", description="View detailed information about a task")
    @app_commands.describe(task_id="The ID of the task to view")
    async def task_details(self, interaction: discord.Interaction, task_id: int):
        """Show detailed information about a task"""
        try:
            task = await self.task_manager.get_task(task_id)
            if not task:
                embed = create_error_embed(f"Task with ID {task_id} not found.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Create detailed embed
            status_emoji = {
                TaskStatus.TODO: "📝",
                TaskStatus.IN_PROGRESS: "⏳",
                TaskStatus.COMPLETED: "✅", 
                TaskStatus.OVERDUE: "⚠️",
                TaskStatus.CANCELLED: "❌"
            }.get(task.status, "📝")
            
            priority_emoji = {
                TaskPriorityLevel.LOW: "🟢",
                TaskPriorityLevel.NORMAL: "🟡",
                TaskPriorityLevel.HIGH: "🟠",
                TaskPriorityLevel.CRITICAL: "🔴"
            }.get(task.priority, "🟡")
            
            embed = discord.Embed(
                title=f"{status_emoji} {task.title}",
                description=task.description if task.description else "*No description provided*",
                color=0x3498db
            )
            
            # Basic info
            embed.add_field(
                name="📊 Status",
                value=f"{status_emoji} {task.status.value}",
                inline=True
            )
            embed.add_field(
                name="⚡ Priority", 
                value=f"{priority_emoji} {task.priority.name}",
                inline=True
            )
            embed.add_field(
                name="📂 Category",
                value=task.category,
                inline=True
            )
            
            # Dates
            tz = pytz.timezone(task.timezone)
            created_dt = datetime.fromtimestamp(task.created_at, tz)
            embed.add_field(
                name="📅 Created",
                value=created_dt.strftime("%m/%d/%Y %I:%M %p"),
                inline=True
            )
            
            if task.due_date:
                due_dt = datetime.fromtimestamp(task.due_date, tz)
                embed.add_field(
                    name="⏰ Due Date",
                    value=due_dt.strftime("%m/%d/%Y %I:%M %p"),
                    inline=True
                )
                
            if task.completed_at:
                completed_dt = datetime.fromtimestamp(task.completed_at, tz)
                embed.add_field(
                    name="✅ Completed",
                    value=completed_dt.strftime("%m/%d/%Y %I:%M %p"),
                    inline=True
                )
                
            # Recurrence info
            if task.recurrence_type != RecurrenceType.NONE:
                recurrence_text = f"{task.recurrence_type.value}"
                if task.recurrence_interval > 1:
                    recurrence_text += f" (every {task.recurrence_interval})"
                embed.add_field(
                    name="🔄 Recurrence",
                    value=recurrence_text,
                    inline=True
                )
                
            embed.add_field(name="🆔 Task ID", value=str(task.id), inline=True)
            embed.set_footer(text=f"Created by user ID: {task.created_by}")
            
            # Add action buttons if user has permissions
            view = None
            if (task.created_by == interaction.user.id or 
                task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]):
                view = TaskActionView(task, interaction.user.id, self.task_manager, self.task_scheduler)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing task details for {task_id}: {e}")
            embed = create_error_embed("Failed to retrieve task details. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # Task command group
    task = app_commands.Group(name="task", description="Task management commands")
    
    @task.command(name="bulk", description="Perform bulk operations on tasks")
    async def bulk_tasks(self, interaction: discord.Interaction):
        """Show bulk task management interface"""
        try:
            # Get user's incomplete tasks
            tasks = await self.task_manager.get_user_tasks(
                interaction.user.id,
                status=None,  # Get all tasks
                limit=100
            )
            
            # Filter to incomplete tasks only
            incomplete_tasks = [
                task for task in tasks 
                if task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]
            ]
            
            if not incomplete_tasks:
                embed = discord.Embed(
                    title="📋 Bulk Task Operations",
                    description="You don't have any incomplete tasks for bulk operations.",
                    color=0x3498db
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Create bulk operation view
            view = BulkTaskActionView(incomplete_tasks, interaction.user.id, self.task_manager)
            
            embed = discord.Embed(
                title="📋 Bulk Task Operations",
                description=f"Select from {len(incomplete_tasks)} incomplete tasks to perform bulk operations.",
                color=0x3498db
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing bulk tasks: {e}")
            embed = create_error_embed("Failed to load bulk task interface. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @task.command(name="overdue", description="View all overdue tasks")
    async def overdue_tasks(self, interaction: discord.Interaction):
        """Show all overdue tasks"""
        try:
            # Get user's tasks and filter overdue
            tasks = await self.task_manager.get_user_tasks(
                interaction.user.id,
                limit=100
            )
            
            current_time = time.time()
            overdue_tasks = [
                task for task in tasks
                if (task.due_date and task.due_date < current_time and 
                    task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
            ]
            
            if not overdue_tasks:
                embed = discord.Embed(
                    title="⚠️ Overdue Tasks",
                    description="You don't have any overdue tasks. Great job! 🎉",
                    color=0x32a956
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Create task list view for overdue tasks
            view = TaskListView(overdue_tasks, interaction.user.id)
            embed = view.create_task_list_embed()
            embed.title = "⚠️ Overdue Tasks"
            embed.color = 0xdc3545  # Red for overdue
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing overdue tasks: {e}")
            embed = create_error_embed("Failed to retrieve overdue tasks. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @task.command(name="upcoming", description="View tasks due in the next 24 hours")
    @app_commands.describe(hours="Number of hours to look ahead (default: 24)")
    async def upcoming_tasks(self, interaction: discord.Interaction, hours: int = 24):
        """Show tasks due in the next N hours"""
        try:
            if hours <= 0 or hours > 168:  # Max 1 week
                embed = create_error_embed("Hours must be between 1 and 168 (1 week).")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Get upcoming tasks
            current_time = time.time()
            future_time = current_time + (hours * 3600)
            
            tasks = await self.task_manager.get_user_tasks(
                interaction.user.id,
                limit=100
            )
            
            upcoming_tasks = [
                task for task in tasks
                if (task.due_date and 
                    current_time <= task.due_date <= future_time and
                    task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
            ]
            
            if not upcoming_tasks:
                embed = discord.Embed(
                    title=f"📅 Upcoming Tasks ({hours}h)",
                    description=f"No tasks due in the next {hours} hours.",
                    color=0x3498db
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            # Sort by due date
            upcoming_tasks.sort(key=lambda t: t.due_date or 0)
            
            # Create task list view for upcoming tasks
            view = TaskListView(upcoming_tasks, interaction.user.id)
            embed = view.create_task_list_embed()
            embed.title = f"📅 Upcoming Tasks ({hours}h)"
            embed.color = 0xff9500  # Orange for upcoming
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing upcoming tasks: {e}")
            embed = create_error_embed("Failed to retrieve upcoming tasks. Please try again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tasks(bot))