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
from utils.reminder_manager_v2 import reminder_manager_v2
from utils.background_task_manager import background_task_manager, TaskPriority

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


class TimezoneView(discord.ui.View):
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


class RemindersV2(commands.Cog):
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
        logger.info("RemindersV2 Cog loaded with event-driven architecture")
    
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
                            timeout=300  # Check every 5 minutes even if no changes
                        )
                        logger.debug("Reminder change detected, checking for new reminders")
                    except asyncio.TimeoutError:
                        logger.debug("Timeout waiting for reminder changes, checking for new reminders")
                else:
                    # Calculate sleep time until next reminder
                    current_time = time.time()
                    sleep_duration = min(next_reminder_time - current_time, 300)  # Max 5 minutes
                    sleep_duration = max(sleep_duration, 1)  # Min 1 second
                    
                    if sleep_duration > 60:
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
    
    reminder = app_commands.Group(name="reminder", description="Manage your reminders")
    
    @reminder.command(name="add", description="Add a reminder with natural language time")
    @app_commands.describe(
        reminder_text="What you want to be reminded about",
        time="When you want to be reminded (e.g., 'tomorrow at 3pm', 'in 2 hours', 'Friday 9am')"
    )
    async def add_reminder(self, interaction: discord.Interaction, reminder_text: str, time: str = None):
        """Add a reminder with natural language time parsing"""
        logger.info(f"User {interaction.user.id} ({interaction.user.name}) is adding a reminder with text: '{reminder_text}' and time: '{time}'")
        
        # Get user's timezone
        user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
        
        # If no time provided, show the modal
        if not time:
            await self._show_reminder_modal(interaction, reminder_text, user_timezone)
            return
        
        # Try to parse the natural language time
        try:
            target_dt = self.reminder_manager.parse_natural_time(time, user_timezone)
            
            if target_dt:
                # Convert to UTC timestamp
                utc_dt = target_dt.astimezone(pytz.UTC)
                trigger_time = utc_dt.timestamp()
                
                # Add the reminder with channel context
                channel_id = interaction.channel_id if interaction.channel else None
                success, message = await self.reminder_manager.add_reminder(
                    interaction.user.id, 
                    reminder_text, 
                    trigger_time, 
                    user_timezone,
                    channel_id
                )
                
                if success:
                    # Format for display
                    readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
                    time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
                    
                    # Show where reminder will be sent
                    location_info = ""
                    if channel_id:
                        location_info = f"\n📍 **Location:** <#{channel_id}>"
                    else:
                        location_info = "\n📍 **Location:** Direct Message"
                    
                    embed = self._create_embed(
                        "Reminder Set ✅",
                        f"Your reminder has been set for **{readable_time}** ({time_until}).\n\n"
                        f"**Reminder:** {reminder_text}{location_info}",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    embed = self._create_embed("Error", message, color=discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # If we couldn't parse the time, show the modal
                await self._show_reminder_modal(interaction, reminder_text, user_timezone)
                
        except Exception as e:
            logger.error(f"Error processing natural language time: {e}", exc_info=True)
            await self._show_reminder_modal(interaction, reminder_text, user_timezone)
    
    @reminder.command(name="list", description="List all your reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        """List all reminders for the user"""
        logger.info(f"User {interaction.user.id} listing reminders")
        
        user_reminders = await self.reminder_manager.get_user_reminders(interaction.user.id)
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            embed = self._create_embed(
                "No Reminders",
                "You don't have any reminders set. Use `/reminder add` to create one!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get user's timezone
        user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
        
        # Format reminders for display
        reminder_list = []
        for idx, (timestamp, message, _, channel_id) in enumerate(user_reminders[:10], 1):  # Show first 10
            utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
            local_time = utc_time.astimezone(pytz.timezone(user_timezone))
            readable_time = local_time.strftime("%b %d at %I:%M %p")
            time_until = self._format_time_until(utc_time.replace(tzinfo=None))
            
            # Show where the reminder will be sent
            location = ""
            if channel_id:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        location = f" 📍 #{channel.name}"
                    else:
                        location = " 📍 Channel (deleted)"
                except:
                    location = " 📍 Channel"
            else:
                location = " 📍 DM"
            
            reminder_list.append(f"**{idx}.** {message}\n   📅 {readable_time} ({time_until}){location}")
        
        description = "\n\n".join(reminder_list)
        if len(user_reminders) > 10:
            description += f"\n\n*...and {len(user_reminders) - 10} more*"
        
        embed = self._create_embed(
            f"Your Reminders ({len(user_reminders)} total)",
            description,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Timezone: {user_timezone}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @reminder.command(name="next", description="Show your next upcoming reminder")
    async def next_reminder(self, interaction: discord.Interaction):
        """Show the user's next upcoming reminder"""
        logger.info(f"User {interaction.user.id} checking next reminder")
        
        user_reminders = await self.reminder_manager.get_user_reminders(interaction.user.id)
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            embed = self._create_embed(
                "No Reminders",
                "You don't have any reminders set. Use `/reminder add` to create one!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get the next reminder (first in sorted list)
        next_timestamp, next_message, _, _ = user_reminders[0]
        
        # Get user's timezone
        user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
        
        # Format the reminder
        utc_time = datetime.utcfromtimestamp(next_timestamp).replace(tzinfo=pytz.UTC)
        local_time = utc_time.astimezone(pytz.timezone(user_timezone))
        readable_time = local_time.strftime("%A, %B %d at %I:%M %p")
        time_until = self._format_time_until(utc_time.replace(tzinfo=None))
        
        embed = self._create_embed(
            "Your Next Reminder ⏰",
            f"**{next_message}**\n\n"
            f"📅 {readable_time}\n"
            f"⏱️ {time_until}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"You have {len(user_reminders)} total reminder{'s' if len(user_reminders) != 1 else ''}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    timezone = app_commands.Group(name="timezone", description="Manage your timezone settings", parent=reminder)
    
    @timezone.command(name="set", description="Set your timezone preferences using a dropdown menu")
    async def set_timezone(self, interaction: discord.Interaction):
        """Set your timezone preferences using a dropdown menu"""
        logger.info(f"User {interaction.user.id} is setting their timezone")
        
        current_tz = await self.reminder_manager.get_user_timezone(interaction.user.id)
        
        # Display current timezone and the dropdown menu
        embed = self._create_embed(
            "Set Your Timezone",
            f"Your timezone is currently set to: **{current_tz}**\n\n"
            f"Please select your timezone from the dropdown menu below, or use the 'Custom Timezone' button if yours is not listed.",
            color=discord.Color.blue()
        )
        
        view = TimezoneView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @timezone.command(name="show", description="Show your current timezone setting")
    async def show_timezone(self, interaction: discord.Interaction):
        """Show the user's current timezone setting"""
        logger.info(f"User {interaction.user.id} checking their timezone")
        
        user_timezone = await self.reminder_manager.get_user_timezone(interaction.user.id)
        
        try:
            # Format the current time in the user's timezone
            local_tz = pytz.timezone(user_timezone)
            local_time = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S")
            
            embed = self._create_embed(
                "Your Timezone",
                f"Your timezone is currently set to: **{user_timezone}**\n\n"
                f"Current time in your timezone: **{local_time}**\n\n"
                f"You can change this with `/reminder timezone set`",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error showing timezone: {e}", exc_info=True)
            embed = self._create_embed(
                "Error",
                f"An error occurred while processing your timezone. Your current setting is: {user_timezone}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def cog_unload(self):
        logger.info("RemindersV2 Cog unloading...")
        if self.reminder_loop_task:
            self.reminder_loop_task.cancel()
        if self.cache_cleanup_task:
            self.cache_cleanup_task.cancel()
        await self.reminder_manager.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(RemindersV2(bot))
    logger.info("RemindersV2 cog setup complete")