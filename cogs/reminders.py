import asyncio
import time
import logging
from datetime import datetime
import discord
from discord import app_commands, ui
from discord.ext import commands
import pytz
from typing import Optional
from utils.embed_utils import create_error_embed
from utils.reminder_manager import reminder_manager_v2
from utils.background_task_manager import background_task_manager, TaskPriority
import os

logger = logging.getLogger(__name__)


class ReminderModal(ui.Modal, title="Set a Reminder"):
    reminder_text = ui.TextInput(
        label="Reminder Text",
        placeholder="What do you want to be reminded about?",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    reminder_date = ui.TextInput(
        label="Date (YYYY-MM-DD)",
        placeholder="2023-12-31",
        required=True
    )
    
    reminder_time = ui.TextInput(
        label="Time (HH:MM) - 24 hour format",
        placeholder="14:30",
        required=True
    )
    
    def __init__(self, cog, user_timezone):
        super().__init__()
        self.cog = cog
        self.user_timezone = user_timezone
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Combine date and time inputs
            date_str = self.reminder_date.value
            time_str = self.reminder_time.value
            datetime_str = f"{date_str} {time_str}:00"
            
            # Parse datetime in user's timezone
            local_tz = pytz.timezone(self.user_timezone)
            local_dt = local_tz.localize(datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S"))
            # Convert to UTC for storage
            utc_dt = local_dt.astimezone(pytz.UTC)
            trigger_time = utc_dt.timestamp()
            
            # Add the reminder with channel context
            channel_id = interaction.channel_id if interaction.channel else None
            success, message = await reminder_manager_v2.add_reminder(
                interaction.user.id, 
                self.reminder_text.value, 
                trigger_time, 
                self.user_timezone,
                channel_id
            )
            
            if success:
                # Format for display
                readable_time = local_dt.strftime("%A, %B %d at %I:%M %p")
                time_until = self.cog._format_time_until(utc_dt.replace(tzinfo=None))
                
                # Show where reminder will be sent
                location_info = ""
                if channel_id:
                    location_info = f"\n📍 **Location:** <#{channel_id}>"
                else:
                    location_info = "\n📍 **Location:** Direct Message"
                
                embed = self.cog._create_embed(
                    "Reminder Set ✅",
                    f"Your reminder has been set for **{readable_time}** ({time_until}).\n\n"
                    f"**Reminder:** {self.reminder_text.value}{location_info}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = self.cog._create_embed(
                    "Error", 
                    message,
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except ValueError:
            embed = self.cog._create_embed(
                "Invalid Format", 
                "Please use the correct date and time format:\n"
                "Date: YYYY-MM-DD (e.g., 2023-12-31)\n"
                "Time: HH:MM in 24-hour format (e.g., 14:30)",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in reminder modal: {e}", exc_info=True)
            embed = self.cog._create_embed(
                "Error", 
                "An unexpected error occurred while setting your reminder.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


# TimezoneView removed - timezone management moved to centralized /timezone commands
class _RemovedTimezoneView:
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.select(
        placeholder="Select your timezone...",
        options=[
            discord.SelectOption(label="US Pacific (Los Angeles)", value="America/Los_Angeles"),
            discord.SelectOption(label="US Mountain (Denver)", value="America/Denver"),
            discord.SelectOption(label="US Central (Chicago)", value="America/Chicago"),
            discord.SelectOption(label="US Eastern (New York)", value="America/New_York"),
            discord.SelectOption(label="UK (London)", value="Europe/London"),
            discord.SelectOption(label="Central Europe (Berlin)", value="Europe/Berlin"),
            discord.SelectOption(label="Eastern Europe (Athens)", value="Europe/Athens"),
            discord.SelectOption(label="India (Kolkata)", value="Asia/Kolkata"),
            discord.SelectOption(label="China (Shanghai)", value="Asia/Shanghai"),
            discord.SelectOption(label="Japan (Tokyo)", value="Asia/Tokyo"),
            discord.SelectOption(label="Australia Eastern (Sydney)", value="Australia/Sydney"),
            discord.SelectOption(label="Australia Western (Perth)", value="Australia/Perth"),
            discord.SelectOption(label="New Zealand (Auckland)", value="Pacific/Auckland"),
            discord.SelectOption(label="Brazil (São Paulo)", value="America/Sao_Paulo"),
            discord.SelectOption(label="Argentina (Buenos Aires)", value="America/Argentina/Buenos_Aires"),
        ]
    )
    async def timezone_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        timezone = select.values[0]
        success, message = await reminder_manager_v2.set_user_timezone(interaction.user.id, timezone)
        
        if success:
            # Show current time in the selected timezone
            tz = pytz.timezone(timezone)
            current_time = datetime.now(tz).strftime("%I:%M %p")
            
            embed = self.cog._create_embed(
                "Timezone Updated ✅",
                f"Your timezone has been set to **{timezone}**\n"
                f"Current time in your timezone: **{current_time}**",
                color=discord.Color.green()
            )
        else:
            embed = self.cog._create_embed("Error", message, color=discord.Color.red())
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="Custom Timezone", style=discord.ButtonStyle.secondary)
    async def custom_timezone(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CustomTimezoneModal(self.cog)
        await interaction.response.send_modal(modal)
        self.stop()


class CustomTimezoneModal(ui.Modal, title="Enter Custom Timezone"):
    timezone_input = ui.TextInput(
        label="Timezone",
        placeholder="e.g., America/New_York, Europe/London, Asia/Tokyo",
        required=True
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        timezone = self.timezone_input.value.strip()
        success, message = await reminder_manager_v2.set_user_timezone(interaction.user.id, timezone)
        
        if success:
            try:
                tz = pytz.timezone(timezone)
                current_time = datetime.now(tz).strftime("%I:%M %p")
                embed = self.cog._create_embed(
                    "Timezone Updated ✅",
                    f"Your timezone has been set to **{timezone}**\n"
                    f"Current time in your timezone: **{current_time}**",
                    color=discord.Color.green()
                )
            except:
                embed = self.cog._create_embed(
                    "Timezone Updated ✅",
                    f"Your timezone has been set to **{timezone}**",
                    color=discord.Color.green()
                )
        else:
            embed = self.cog._create_embed("Error", message, color=discord.Color.red())
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ReminderListView(discord.ui.View):
    def __init__(self, cog, user_id: int, page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.page = page
        self.reminders_per_page = 5
        self._update_buttons()
    
    def _update_buttons(self):
        # Update button states based on current page
        self.previous_button.disabled = self.page == 0
    
    async def _get_user_reminders(self):
        """Get reminders for the user"""
        return await reminder_manager_v2.get_user_reminders(self.user_id)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = self.cog._create_embed(
                "Access Denied",
                "This isn't your reminder menu!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = self.cog._create_embed(
                "Access Denied",
                "This isn't your reminder menu!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        user_reminders = await self._get_user_reminders()
        total_pages = (len(user_reminders) - 1) // self.reminders_per_page + 1
        
        self.page = min(total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_loop_task = None
        self.cache_cleanup_task = None
        self.reminder_manager = reminder_manager_v2
    
    def _create_embed(self, title, description, color=discord.Color.blue()):
        """Create a standardized embed for responses"""
        # Use standardized error format for red/error embeds
        if color == discord.Color.red():
            return create_error_embed(description)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        return embed
    
    def _format_time_until(self, target_dt):
        """Format the time until a future datetime in a human-readable format"""
        now = datetime.now()
        delta = target_dt - now
        
        # If the time has passed
        if delta.total_seconds() < 0:
            return "now"
        
        # Calculate time components
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        # Format the string
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 and days == 0:  # Only show minutes if less than a day away
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        
        # Smart formatting
        if not parts:
            return "in a moment"
        elif len(parts) == 1:
            return f"in {parts[0]}"
        else:
            return f"in {' and '.join(parts[:2])}"
    
    def _format_time_since(self, past_dt):
        """Format the time since a past datetime in a human-readable format"""
        if past_dt.tzinfo:
            now = datetime.now(past_dt.tzinfo)
        else:
            now = datetime.now()
            
        delta = now - past_dt
        
        if delta.total_seconds() < 60:
            return "1 minute ago"
            
        if past_dt.date() == now.date():
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            
            if hours > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            else:
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            
        if (now.date() - past_dt.date()).days == 1:
            return "yesterday"
            
        if delta.days < 7:
            return f"last {past_dt.strftime('%A')}"
            
        if now.month == past_dt.month and now.year == past_dt.year:
            return f"{delta.days} days ago"
            
        years = now.year - past_dt.year
        months = now.month - past_dt.month
        if months < 0:
            years -= 1
            months += 12
            
        if years > 0:
            return f"{years} year{'s' if years != 1 else ''} ago" if months == 0 else f"{years} year{'s' if years != 1 else ''} and {months} month{'s' if months != 1 else ''} ago"
        else:
            return f"{months} month{'s' if months != 1 else ''} ago"
    
    async def cog_load(self):
        await self.reminder_manager.initialize()
        self.reminder_loop_task = asyncio.create_task(self.event_driven_reminder_loop())
        self.cache_cleanup_task = asyncio.create_task(self.cache_cleanup_loop())
        logger.info("Reminders Cog loaded with event-driven architecture")
    
    async def event_driven_reminder_loop(self):
        """Event-driven reminder loop that responds immediately to changes"""
        logger.info("Event-driven reminder loop started")
        
        while True:
            try:
                # Get due reminders
                due_reminders = await self.reminder_manager.get_due_reminders()
                
                # Process each due reminder
                for trigger_time, user_id, message, user_tz, channel_id in due_reminders:
                    trigger_readable = datetime.utcfromtimestamp(trigger_time).strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"Triggering reminder - User: {user_id}, Reminder time: {trigger_readable} UTC, Text: '{message}'")
                    
                    try:
                        # Format reminder time in user's timezone
                        trigger_time_utc = datetime.utcfromtimestamp(trigger_time).replace(tzinfo=pytz.UTC)
                        user_timezone = pytz.timezone(user_tz)
                        local_time = trigger_time_utc.astimezone(user_timezone).strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Create embed for the reminder
                        reminder_set_time_utc = datetime.utcfromtimestamp(trigger_time - 10).replace(tzinfo=pytz.UTC)
                        reminder_set_time_local = reminder_set_time_utc.astimezone(user_timezone)
                        time_since = self._format_time_since(reminder_set_time_local)
                        readable_set_date = reminder_set_time_local.strftime("%Y-%m-%d at %I:%M %p")
                        
                        embed = self._create_embed(
                            "Reminder ⏰",
                            f"**{message}**\n\nSet {time_since} on {readable_set_date}",
                            color=discord.Color.gold()
                        )
                        
                        # Send to channel if available, otherwise DM
                        if channel_id:
                            try:
                                channel = await self.bot.fetch_channel(channel_id)
                                await channel.send(f"<@{user_id}>", embed=embed)
                                logger.info(f"Successfully sent reminder to channel {channel_id} for user {user_id}")
                            except (discord.NotFound, discord.Forbidden) as e:
                                logger.warning(f"Cannot send to channel {channel_id}, falling back to DM: {e}")
                                # Fall back to DM
                                user = await self.bot.fetch_user(user_id)
                                await user.send(embed=embed)
                                logger.info(f"Successfully sent reminder via DM to user {user_id} ({user.name})")
                        else:
                            # No channel context, send DM
                            # Skip if user has DM failures
                            if self.reminder_manager.is_dm_failed_user(user_id):
                                logger.warning(f"Skipping DM for user {user_id} (previous failures)")
                                continue
                                
                            user = await self.bot.fetch_user(user_id)
                            await user.send(embed=embed)
                            logger.info(f"Successfully sent reminder via DM to user {user_id} ({user.name})")
                        
                    except discord.Forbidden:
                        logger.warning(f"Cannot send DM to user {user_id} (forbidden - likely has DMs disabled)")
                        self.reminder_manager.add_dm_failed_user(user_id)
                        
                    except Exception as e:
                        logger.error(f"Failed to send reminder to user {user_id}: {e}", exc_info=True)
                    
                    # Mark reminder as sent
                    await self.reminder_manager.mark_reminder_sent(trigger_time)
                
                # Get next reminder time for smart sleeping
                next_reminder_time = await self.reminder_manager.get_next_reminder_time()
                
                if next_reminder_time is None:
                    # No reminders scheduled, wait for new ones or check periodically
                    try:
                        # Wait for either a new reminder or a timeout
                        await asyncio.wait_for(
                            self.reminder_manager.wait_for_reminder_change(),
                            timeout=30  # Check every 30 seconds even if no changes
                        )
                        logger.debug("Reminder change detected, checking for new reminders")
                    except asyncio.TimeoutError:
                        logger.debug("Timeout waiting for reminder changes, checking for new reminders")
                else:
                    # Calculate sleep time until next reminder
                    current_time = time.time()
                    sleep_duration = min(next_reminder_time - current_time, 60)  # Max 60 seconds
                    sleep_duration = max(sleep_duration, 1)  # Min 1 second
                    
                    if sleep_duration > 5:
                        # For longer sleeps, also listen for new reminders
                        try:
                            await asyncio.wait_for(
                                self.reminder_manager.wait_for_reminder_change(),
                                timeout=sleep_duration
                            )
                            logger.debug("Reminder change detected during sleep, waking up early")
                        except asyncio.TimeoutError:
                            logger.debug(f"Woke up after {sleep_duration:.1f} seconds")
                    else:
                        # For short sleeps, just sleep
                        logger.debug(f"Sleeping for {sleep_duration:.1f} seconds until next reminder")
                        await asyncio.sleep(sleep_duration)
                
            except Exception as e:
                logger.error(f"Error in event-driven reminder loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Sleep longer on error to prevent spam
    
    async def cache_cleanup_loop(self):
        """Background task to clean up expired cache entries and database"""
        while True:
            try:
                # Clean up expired reminders every hour using background task manager
                await asyncio.sleep(3600)  # 1 hour
                
                # Submit cleanup as background task
                await background_task_manager.submit_function(
                    self.reminder_manager._background_cleanup_expired,
                    task_id=f"cleanup_expired_{int(time.time())}",
                    priority=TaskPriority.LOW
                )
                
                # Log background task manager metrics
                metrics = background_task_manager.get_metrics()
                active_tasks = len(background_task_manager.get_active_tasks())
                
                logger.info(
                    f"Background task metrics - Active: {active_tasks}, "
                    f"Total: {metrics['total_tasks']}, "
                    f"Success rate: {metrics['successful_tasks'] / max(metrics['total_tasks'], 1) * 100:.1f}%"
                )
                
            except Exception as e:
                logger.error(f"Error in cache cleanup loop: {e}", exc_info=True)
                await asyncio.sleep(600)  # Wait 10 minutes on error
    
    async def _show_reminder_modal(self, interaction: discord.Interaction, pre_filled_text: str = "", user_timezone: str = None):
        """Show the reminder modal with optional pre-filled text"""
        if user_timezone is None:
            user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
            
        modal = ReminderModal(self, user_timezone)
        if pre_filled_text:
            modal.reminder_text.default = pre_filled_text
        
        await interaction.response.send_modal(modal)
    
    # Manual reminder commands removed - use /reminder natural language interface instead
    # 
    # Example usage:
    # /reminder set a reminder to call mom tomorrow at 3pm
    # /reminder show me my reminders
    # /reminder cancel the reminder about the dentist appointment
    # /reminder what's my next reminder?
    
    # timezone commands removed - now available as centralized /timezone commands
    
    @app_commands.command(name="reminder", description="Natural language reminder management with AI assistant")
    @app_commands.describe(
        prompt="Your reminder-related request or question",
        model="AI model to use (optional)"
    )
    async def reminder_chat(
        self, 
        interaction: discord.Interaction, 
        prompt: str,
        model: Optional[str] = None
    ):
        """Reminder-focused AI chat interface"""
        await interaction.response.defer(thinking=True)
        
        try:
            # Get user's current timezone and add to context
            user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
            local_tz = pytz.timezone(user_timezone)
            current_time = datetime.now(local_tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
            
            # Get user's reminders for context
            user_reminders = await self.reminder_manager.get_user_reminders(interaction.user.id)
            
            # Create reminder context
            reminder_context = []
            if user_reminders:
                reminder_context.append(f"\nCurrent Reminders ({len(user_reminders)} total):")
                for idx, (timestamp, message, _, channel_id) in enumerate(user_reminders[:5], 1):
                    utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
                    local_time = utc_time.astimezone(local_tz)
                    readable_time = local_time.strftime("%a %m/%d at %I:%M %p")
                    location = f" (#{self.bot.get_channel(channel_id).name})" if channel_id and self.bot.get_channel(channel_id) else " (DM)" if not channel_id else " (channel)"
                    reminder_context.append(f"  {idx}. '{message}' - {readable_time}{location}")
                
                if len(user_reminders) > 5:
                    reminder_context.append(f"  ...and {len(user_reminders) - 5} more")
            else:
                reminder_context.append("\nCurrent Reminders: None set")
            
            reminder_context_str = "\n".join(reminder_context)
            
            # Create reminder-specific system prompt
            reminder_system_prompt = f"""You are a personal reminder assistant. You help users manage SIMPLE NOTIFICATIONS through natural language conversation.

WHAT REMINDERS ARE FOR:
- Simple time-based notifications: "Remind me to call mom at 3pm"
- One-time alerts: "Remind me to take medicine in 2 hours"  
- Quick notifications: "Remind me about the meeting tomorrow at 9am"
- Personal alerts that don't need tracking or status updates

WHAT REMINDERS ARE NOT FOR:
- Work tasks that need tracking, status updates, or project management
- Complex tasks with due dates, priorities, or assignments
- Recurring work items or project deliverables
- Things that need "completion" tracking or progress updates

WHEN TO SUGGEST TASKS INSTEAD:
If users request something that needs tracking or has work-related context, suggest:
"This sounds like a task that needs tracking. Use /task to create a proper task with due dates and notifications, or I can help you set a simple reminder instead."

AVAILABLE TOOL:
**manage_reminders**: Complete reminder management (set, list, cancel, search, update, cancel multiple, get next)

ENHANCED TIME PARSING:
The system now supports advanced time expressions including:
- "6pm tonight", "tonight at 6pm", "midnight tonight"  
- "3pm today", "today at 3pm"
- All previous patterns: "tomorrow at 3pm", "in 2 hours", "Friday morning"

FUNCTIONALITY:
- Set reminders with natural language time 
- List, search, and cancel existing reminders
- Update reminder text or time
- Cancel multiple reminders at once
- Get next upcoming reminder
- Support for both channel and DM delivery

IMPORTANT GUIDELINES:
- Parse natural time expressions intelligently using user's timezone
- **EXECUTE ACTIONS DIRECTLY** - Don't ask for confirmation, just create/manage reminders immediately
- When listing reminders, show them in a readable format with relative times
- For updates, clearly explain what changed
- Be helpful with time zone awareness - user's current time is provided
- Only ask clarifying questions if the request is genuinely ambiguous or missing critical information
- Keep reminders simple and focused on one-shot notifications
- Default to current channel for new reminders unless user specifies DM
- If user asks for task/work management, suggest they use /task instead

USER CONTEXT:
- User: {interaction.user.name} (ID: {interaction.user.id})
- Channel: {getattr(interaction.channel, 'name', 'DM')} (ID: {interaction.channel_id})
- User's current time: {current_time}
- User's timezone: {user_timezone}{reminder_context_str}

Remember: You have access to the user's current reminders above. When they reference reminders by content or position, match them to existing reminders."""

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
            import os
            original_system_prompt = os.environ.get('SYSTEM_PROMPT', '')
            os.environ['SYSTEM_PROMPT'] = reminder_system_prompt
            
            try:
                # Process through AI with reminder management focus
                username = interaction.user.name
                formatted_prompt = f"{username}: {prompt}"
                
                # Use the AI processing with reminder management focus and restricted tools
                await ai_commands._process_ai_request(
                    formatted_prompt, 
                    model or "gemini-2.5-flash-preview",  # Default model
                    interaction=interaction, 
                    attachments=[], 
                    fun=False, 
                    web_search=False, 
                    deep_research=False, 
                    tool_calling=True,  # Enable tools for reminder management
                    max_tokens=4000,
                    allowed_tools=["manage_reminders"]  # Restrict to only reminder tools
                )
            finally:
                # Restore original system prompt
                os.environ['SYSTEM_PROMPT'] = original_system_prompt
                
        except Exception as e:
            logger.error(f"Error in reminder chat: {e}")
            embed = discord.Embed(
                title="❌ Error", 
                description="An error occurred while processing your reminder request.", 
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
    
    async def cog_unload(self):
        logger.info("Reminders Cog unloading...")
        if self.reminder_loop_task:
            self.reminder_loop_task.cancel()
        if self.cache_cleanup_task:
            self.cache_cleanup_task.cancel()
        await self.reminder_manager.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
    logger.info("Reminders cog setup complete")