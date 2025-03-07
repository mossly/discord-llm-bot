import asyncio
import time
import logging
import json
import os
from datetime import datetime, timedelta
import discord
from discord import app_commands, ui
from discord.ext import commands
from collections import defaultdict
import pytz
from typing import Dict, Optional

# Set up enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("reminders.log")
    ]
)
logger = logging.getLogger(__name__)

# Constants
MAX_REMINDERS_PER_USER = 25
MIN_REMINDER_INTERVAL = 60  # Minimum 60 seconds between reminders
DEFAULT_TIMEZONE = "Pacific/Auckland"  # New Zealand timezone (GMT+13)

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
            
            # Check if the reminder is for the past
            now = time.time()
            if trigger_time <= now:
                logger.warning(f"User {interaction.user.id} attempted to set a reminder for the past: {datetime_str} in {self.user_timezone} (Now: {datetime.now()})")
                embed = self.cog._create_embed(
                    "Invalid Time", 
                    "You can't set reminders for the past! Please choose a future time.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Check rate limiting for this user
            user_reminders = [r for t, (uid, r, _) in self.cog.reminders.items() if uid == interaction.user.id]
            if len(user_reminders) >= MAX_REMINDERS_PER_USER:
                logger.warning(f"User {interaction.user.id} hit max reminders limit ({MAX_REMINDERS_PER_USER})")
                embed = self.cog._create_embed(
                    "Too Many Reminders", 
                    f"You already have {MAX_REMINDERS_PER_USER} reminders set. Please remove some before adding more.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Check if there's already a reminder at this exact time for this user
            if trigger_time in self.cog.reminders and self.cog.reminders[trigger_time][0] == interaction.user.id:
                logger.warning(f"User {interaction.user.id} attempted to set duplicate reminder at {datetime_str}")
                embed = self.cog._create_embed(
                    "Duplicate Reminder", 
                    "You already have a reminder set for this exact time. Please choose a different time.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # All checks passed, add the reminder
            self.cog.reminders[trigger_time] = (interaction.user.id, self.reminder_text.value, self.user_timezone)
            self.cog._save_reminders()
            
            # Display times in the user's timezone
            local_readable_time = local_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Get current time in user's timezone
            current_local_time = datetime.now(local_tz)
            
            # Calculate time until reminder
            time_until = self.cog._format_time_until(utc_dt.replace(tzinfo=None))
            
            logger.info(f"Reminder set - User: {interaction.user.id}, Current time: {datetime.now()}, Reminder time: {local_readable_time} in {self.user_timezone}, Text: '{self.reminder_text.value}'")
            
            embed = self.cog._create_embed(
                "Reminder Set ✅",
                f"Your reminder has been set for **{local_dt.strftime('%A, %B %d at %I:%M %p')}** ({time_until}).\n\n"
                f"**Reminder:** {self.reminder_text.value}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError as e:
            logger.error(f"Date parsing error: {e} for input date={self.reminder_date.value}, time={self.reminder_time.value}")
            embed = self.cog._create_embed(
                "Invalid Format",
                "Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Error in ReminderModal: {error}", exc_info=True)
        embed = self.cog._create_embed(
            "Error",
            "An error occurred while processing your reminder.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TimezoneSelect(ui.Select):
    def __init__(self, cog):
        self.cog = cog
        
        # Define common timezones with descriptions including the current time
        self.timezone_options = [
            ("Pacific/Auckland", "New Zealand (Auckland)"),
            ("Australia/Sydney", "Australia (Sydney)"),
            ("Asia/Tokyo", "Japan (Tokyo)"),
            ("Asia/Shanghai", "China (Shanghai)"),
            ("Asia/Kolkata", "India (Kolkata)"),
            ("Europe/London", "Europe (London)"),
            ("Europe/Paris", "Europe (Paris)"),
            ("America/New_York", "US/Canada (Eastern)"),
            ("America/Chicago", "US/Canada (Central)"),
            ("America/Los_Angeles", "US/Canada (Pacific)"),
            ("Pacific/Honolulu", "Hawaii"),
            ("UTC", "UTC (Coordinated Universal Time)")
        ]
        
        # Create options with current time in description
        options = []
        for tz_name, label in self.timezone_options:
            tz = pytz.timezone(tz_name)
            current_time = datetime.now(tz).strftime("%H:%M")
            options.append(
                discord.SelectOption(
                    label=label,
                    description=f"{tz_name} (Current time: {current_time})",
                    value=tz_name
                )
            )
        
        super().__init__(
            placeholder="Choose your timezone...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        timezone_str = self.values[0]
        
        # Save the user's timezone preference
        self.cog.user_timezones[interaction.user.id] = timezone_str
        self.cog._save_user_timezones()
        
        # Format the current time in the user's timezone
        local_time = datetime.now(pytz.timezone(timezone_str)).strftime("%Y-%m-%d %H:%M:%S")
        
        embed = self.cog._create_embed(
            "Timezone Set",
            f"✅ Your timezone has been set to **{timezone_str}**.\n"
            f"Current time in your timezone: **{local_time}**",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class TimezoneView(ui.View):
    def __init__(self, cog, *, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.add_item(TimezoneSelect(cog))
        
    @ui.button(label="Custom Timezone", style=discord.ButtonStyle.secondary, row=1)
    async def custom_timezone(self, interaction: discord.Interaction, button: ui.Button):
        # For users who need a timezone not in the dropdown
        modal = CustomTimezoneModal(self.cog)
        await interaction.response.send_modal(modal)


class CustomTimezoneModal(ui.Modal, title="Set Custom Timezone"):
    timezone_input = ui.TextInput(
        label="Timezone",
        placeholder="e.g., Pacific/Auckland, America/New_York",
        required=True
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            timezone_str = self.timezone_input.value
            
            # Validate timezone
            try:
                _ = pytz.timezone(timezone_str)
            except pytz.exceptions.UnknownTimeZoneError:
                embed = self.cog._create_embed(
                    "Invalid Timezone",
                    f"The timezone '{timezone_str}' is not valid. Please use a valid timezone name like 'Pacific/Auckland' or 'America/New_York'.\n\n"
                    f"You can find a list of valid timezones here:\nhttps://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Save the user's timezone preference
            self.cog.user_timezones[interaction.user.id] = timezone_str
            self.cog._save_user_timezones()
            
            # Format the current time in the user's timezone
            local_time = datetime.now(pytz.timezone(timezone_str)).strftime("%Y-%m-%d %H:%M:%S")
            
            embed = self.cog._create_embed(
                "Timezone Set",
                f"✅ Your timezone has been set to **{timezone_str}**.\n"
                f"Current time in your timezone: **{local_time}**",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting timezone: {e}", exc_info=True)
            embed = self.cog._create_embed(
                "Error",
                "An error occurred while setting your timezone.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class CancelReminderView(ui.View):
    def __init__(self, cog, user_id, *, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.page = 0
        self.reminders_per_page = 5
        
        # Initialize buttons based on user's reminders
        self._update_buttons()
    
    def _update_buttons(self):
        # Clear existing buttons
        self.clear_items()
        
        # Get user's preferred timezone
        user_timezone = self.cog.user_timezones.get(self.user_id, DEFAULT_TIMEZONE)
        local_tz = pytz.timezone(user_timezone)
        
        # Get user's reminders
        user_reminders = sorted(
            [(ts, msg, tz) for ts, (uid, msg, tz) in self.cog.reminders.items() if uid == self.user_id],
            key=lambda x: x[0]
        )
        
        if not user_reminders:
            return
        
        # Calculate pages
        total_pages = (len(user_reminders) - 1) // self.reminders_per_page + 1
        start_idx = self.page * self.reminders_per_page
        end_idx = min(start_idx + self.reminders_per_page, len(user_reminders))
        
        # Add reminder cancel buttons for this page
        for i in range(start_idx, end_idx):
            ts, msg, _ = user_reminders[i]
            
            # Convert UTC timestamp to user's timezone
            utc_dt = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)
            local_dt = utc_dt.astimezone(local_tz)
            time_str = local_dt.strftime("%Y-%m-%d %H:%M")
            
            # Truncate message if too long
            display_msg = msg if len(msg) <= 30 else msg[:27] + "..."
            button_label = f"{time_str} - {display_msg}"
            
            button = ui.Button(style=discord.ButtonStyle.danger, label=button_label, custom_id=f"cancel_{ts}")
            button.callback = self.make_callback(ts)
            self.add_item(button)
        
        # Add navigation buttons if needed
        if total_pages > 1:
            # Previous page button
            prev_button = ui.Button(
                style=discord.ButtonStyle.secondary, 
                label="Previous", 
                disabled=(self.page == 0),
                row=4
            )
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
            
            # Page indicator
            page_indicator = ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"Page {self.page + 1}/{total_pages}",
                disabled=True,
                row=4
            )
            self.add_item(page_indicator)
            
            # Next page button
            next_button = ui.Button(
                style=discord.ButtonStyle.secondary, 
                label="Next", 
                disabled=(self.page == total_pages - 1),
                row=4
            )
            next_button.callback = self.next_page
            self.add_item(next_button)
    
    def make_callback(self, timestamp):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = self.cog._create_embed(
                    "Access Denied",
                    "This isn't your reminder menu!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            self.cog.reminders.pop(timestamp, None)
            self.cog._save_reminders()
            
            # Re-render the view with updated buttons
            self._update_buttons()
            
            if not self.children:  # No buttons left
                embed = self.cog._create_embed(
                    "No Reminders", 
                    "You have no more reminders.",
                    color=discord.Color.blue()
                )
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                embed = self.cog._create_embed(
                    "Reminder Cancelled", 
                    "Reminder cancelled! Here are your remaining reminders:",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    async def previous_page(self, interaction: discord.Interaction):
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
    
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = self.cog._create_embed(
                "Access Denied",
                "This isn't your reminder menu!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        user_reminders = [r for t, (uid, r, _) in self.cog.reminders.items() if uid == self.user_id]
        total_pages = (len(user_reminders) - 1) // self.reminders_per_page + 1
        
        self.page = min(total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)

class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders = {}  # {timestamp: (user_id, message, timezone)}
        self.user_timezones = {}  # {user_id: timezone_string}
        self.task = None
        self.reminders_file = "reminders.json"
        self.timezones_file = "user_timezones.json"
        self.dm_failed_users = set()  # Track users with failed DMs
        self._load_user_timezones()
        self._load_reminders()

    def _create_embed(self, title, description, color=discord.Color.blue()):
        """Create a standardized embed for responses"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        return embed

    def _load_user_timezones(self):
        """Load user timezones from disk"""
        if os.path.exists(self.timezones_file):
            try:
                with open(self.timezones_file, 'r') as f:
                    # User IDs need to be converted from strings to integers
                    data = json.load(f)
                    self.user_timezones = {
                        int(uid): tz for uid, tz in data.items()
                    }
                logger.info(f"Loaded {len(self.user_timezones)} user timezone preferences")
            except Exception as e:
                logger.error(f"Failed to load user timezones: {e}", exc_info=True)
                self.user_timezones = {}
        else:
            self.user_timezones = {}

    def _save_user_timezones(self):
        """Save user timezones to disk"""
        try:
            # Convert the dictionary to a format that can be JSON serialized
            data = {
                str(uid): tz for uid, tz in self.user_timezones.items()
            }
            with open(self.timezones_file, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved {len(self.user_timezones)} user timezone preferences")
        except Exception as e:
            logger.error(f"Failed to save user timezones: {e}", exc_info=True)

    def _load_reminders(self):
        """Load reminders from disk"""
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r') as f:
                    # JSON can't store numbers as keys, so we convert back from strings
                    data = json.load(f)
                    self.reminders = {
                        float(ts): (int(uid), msg, tz) 
                        for ts, (uid, msg, tz) in data.items()
                    }
                logger.info(f"Loaded {len(self.reminders)} reminders from disk")
                
                # Clean up past reminders that might have been missed while the bot was offline
                now = time.time()
                expired = [ts for ts in self.reminders if float(ts) <= now]
                for ts in expired:
                    logger.warning(f"Removing expired reminder from load: {datetime.utcfromtimestamp(float(ts))}")
                    self.reminders.pop(float(ts), None)
                
                if expired:
                    self._save_reminders()
                    logger.info(f"Cleaned up {len(expired)} expired reminders")
                
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}", exc_info=True)
                self.reminders = {}
        else:
            self.reminders = {}

    def _save_reminders(self):
        """Save reminders to disk"""
        try:
            # Convert the dictionary to a format that can be JSON serialized
            # JSON keys must be strings, so convert the timestamps
            data = {
                str(ts): [uid, msg, tz] 
                for ts, (uid, msg, tz) in self.reminders.items()
            }
            with open(self.reminders_file, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved {len(self.reminders)} reminders to disk")
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}", exc_info=True)

    def _format_time_until(self, target_dt):
        """Format the time difference between now and target datetime in a human-readable format"""
        now = datetime.now()
        delta = target_dt - now
        
        # Handle future times
        if delta.total_seconds() > 0:
            years, remainder = divmod(delta.days, 365)
            months, days = divmod(remainder, 30)
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            seconds = delta.seconds % 60
            
            parts = []
            if years > 0:
                parts.append(f"{years} year{'s' if years != 1 else ''}")
            if months > 0:
                parts.append(f"{months} month{'s' if months != 1 else ''}")
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds > 0 and not parts:  # Only include seconds if less than a minute
                parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
                
            # Smart formatting
            if not parts:
                return "in a moment"
            elif len(parts) == 1:
                return f"in {parts[0]}"
            else:
                # Return a maximum of 2 units for readability
                return f"in {' and '.join(parts[:2])}"
        
        return "now"
        
    def _format_time_since(self, past_dt):
        """Format the time since a past datetime in a human-readable format"""
        # Ensure past_dt has timezone info if it's a timezone-aware datetime
        if past_dt.tzinfo:
            now = datetime.now(past_dt.tzinfo)  # Use same timezone as past_dt
        else:
            now = datetime.now()  # Use naive datetime for naive input
            
        delta = now - past_dt
        
        # For very recent times (within a minute)
        if delta.total_seconds() < 60:
            return "1 minute ago"
            
        # For times within today
        if past_dt.date() == now.date():
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            
            if hours > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            else:
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            
        # For yesterday
        if (now.date() - past_dt.date()).days == 1:
            return "yesterday"
            
        # For within the last week
        if delta.days < 7:
            return f"last {past_dt.strftime('%A')}"  # Day name
            
        # For within the current month
        if now.month == past_dt.month and now.year == past_dt.year:
            return f"{delta.days} days ago"
            
        # For longer periods
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
        self.task = asyncio.create_task(self.reminder_loop())
        logger.info("Reminder Cog loaded and reminder loop started")

    async def reminder_loop(self):
        """Main loop to check and trigger reminders"""
        logger.info("Reminder loop started")
        while True:
            try:
                current_time = time.time()
                now_readable = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Find reminders that need to be triggered
                to_trigger = []
                for trigger_time, (user_id, message, user_tz) in self.reminders.items():
                    if trigger_time <= current_time:
                        to_trigger.append((trigger_time, user_id, message, user_tz))
                
                # Process triggered reminders
                for trigger_time, user_id, message, user_tz in to_trigger:
                    trigger_readable = datetime.utcfromtimestamp(trigger_time).strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"Triggering reminder - User: {user_id}, Current time: {now_readable}, Reminder time: {trigger_readable} UTC, Text: '{message}'")
                    
                    try:
                        # Skip sending DM if user previously had DM failures
                        if user_id in self.dm_failed_users:
                            logger.warning(f"Skipping DM for user {user_id} (previous failures)")
                            continue
                            
                        user = await self.bot.fetch_user(user_id)
                        
                        # Format reminder time in user's timezone
                        trigger_time_utc = datetime.utcfromtimestamp(trigger_time).replace(tzinfo=pytz.UTC)
                        user_timezone = pytz.timezone(user_tz)
                        local_time = trigger_time_utc.astimezone(user_timezone).strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Create embed for the reminder with info about when it was set
                        # Use the user's timezone for displaying set time
                        reminder_set_time_utc = datetime.utcfromtimestamp(trigger_time - 10).replace(tzinfo=pytz.UTC)  # Approximate time when reminder was set
                        reminder_set_time_local = reminder_set_time_utc.astimezone(user_timezone)
                        time_since = self._format_time_since(reminder_set_time_local)
                        readable_set_date = reminder_set_time_local.strftime("%Y-%m-%d at %I:%M %p")
                        
                        embed = self._create_embed(
                            "Reminder ⏰",
                            f"**{message}**\n\nSet {time_since} on {readable_set_date}",
                            color=discord.Color.gold()
                        )
                        await user.send(embed=embed)
                        logger.info(f"Successfully sent reminder to user {user_id} ({user.name})")
                        
                    except discord.Forbidden:
                        logger.warning(f"Cannot send DM to user {user_id} (forbidden - likely has DMs disabled)")
                        self.dm_failed_users.add(user_id)  # Track this user as having DM issues
                        
                    except Exception as e:
                        logger.error(f"Failed to send reminder to user {user_id}: {e}", exc_info=True)
                    
                    # Remove the triggered reminder
                    self.reminders.pop(trigger_time, None)
                
                # Save if any reminders were triggered
                if to_trigger:
                    self._save_reminders()
                
                # Sleep briefly before next check
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in reminder loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Sleep a bit longer on error

    def get_user_timezone(self, user_id: int) -> str:
        """Get the timezone for a user, or return the default timezone"""
        return self.user_timezones.get(user_id, DEFAULT_TIMEZONE)

    reminder = app_commands.Group(name="reminder", description="Manage your reminders")

    @reminder.command(name="add", description="Add a reminder with natural language time")
    @app_commands.describe(
        reminder_text="What you want to be reminded about",
        time="When you want to be reminded (e.g., 'tomorrow at 3pm', 'in 2 hours', 'Friday 9am')"
    )
    async def add_reminder(self, interaction: discord.Interaction, reminder_text: str, time: str = None):
        """Add a reminder with natural language time parsing"""
        # Log the attempt
        logger.info(f"User {interaction.user.id} ({interaction.user.name}) is adding a reminder with text: '{reminder_text}' and time: '{time}'")
        
        # Check if user has too many reminders
        user_reminders = [r for t, (uid, r, _) in self.reminders.items() if uid == interaction.user.id]
        if len(user_reminders) >= MAX_REMINDERS_PER_USER:
            logger.warning(f"User {interaction.user.id} hit max reminders limit ({MAX_REMINDERS_PER_USER})")
            embed = self._create_embed(
                "Too Many Reminders", 
                f"You already have {MAX_REMINDERS_PER_USER} reminders set. Please remove some before adding more.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Get user's timezone
        user_timezone = self.get_user_timezone(interaction.user.id)
        local_tz = pytz.timezone(user_timezone)
        
        # If time is provided, try to parse it directly
        if time:
            await self._process_natural_language_time(interaction, reminder_text, time, user_timezone)
        else:
            # If no time is provided, use the modal with improved defaults
            await self._show_reminder_modal(interaction, reminder_text, user_timezone)
            
    async def _process_natural_language_time(self, interaction, reminder_text, time_str, user_timezone):
        """Process natural language time input"""
        try:
            # Get current time in user's timezone to use as reference
            local_tz = pytz.timezone(user_timezone)
            now = datetime.now(local_tz)
            
            # Handle special keywords
            time_str = time_str.lower().strip()
            target_dt = None
            
            # Handle common time expressions
            if time_str == "tomorrow":
                target_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            elif time_str == "tonight":
                target_dt = now.replace(hour=20, minute=0, second=0, microsecond=0)
            elif time_str == "noon" or time_str == "midday":
                if now.hour >= 12:  # If it's already past noon, use tomorrow
                    target_dt = (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
                else:
                    target_dt = now.replace(hour=12, minute=0, second=0, microsecond=0)
            elif time_str == "midnight":
                target_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_str.startswith("in "):
                # Handle "in X minutes/hours/days/weeks/months"
                parts = time_str[3:].split()
                if len(parts) >= 2:
                    try:
                        amount = int(parts[0])
                        unit = parts[1].lower()
                        if unit.startswith("minute"):
                            target_dt = now + timedelta(minutes=amount)
                        elif unit.startswith("hour"):
                            target_dt = now + timedelta(hours=amount)
                        elif unit.startswith("day"):
                            target_dt = now + timedelta(days=amount)
                        elif unit.startswith("week"):
                            target_dt = now + timedelta(weeks=amount)
                        elif unit.startswith("month"):
                            # Approximate a month as 30 days
                            target_dt = now + timedelta(days=30*amount)
                    except ValueError:
                        pass
            elif "tomorrow" in time_str and ("at" in time_str or ":" in time_str):
                # Handle "tomorrow at X:YY" or "tomorrow X:YY"
                time_part = time_str.split("at")[-1].strip() if "at" in time_str else time_str.split("tomorrow")[-1].strip()
                time_part = time_part.replace("am", " AM").replace("pm", " PM")
                try:
                    # Try different time formats
                    time_formats = ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]
                    parsed_time = None
                    
                    for fmt in time_formats:
                        try:
                            parsed_time = datetime.strptime(time_part, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if parsed_time:
                        tomorrow = now + timedelta(days=1)
                        target_dt = tomorrow.replace(
                            hour=parsed_time.hour, 
                            minute=parsed_time.minute, 
                            second=0, 
                            microsecond=0
                        )
                except ValueError:
                    pass
            elif any(day in time_str.lower() for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
                # Handle day names (e.g., "Friday at 3pm")
                day_mapping = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                
                target_day = None
                for day, day_num in day_mapping.items():
                    if day in time_str.lower():
                        target_day = day_num
                        break
                
                if target_day is not None:
                    # Calculate days until the next occurrence of this day
                    current_day = now.weekday()
                    days_ahead = (target_day - current_day) % 7
                    if days_ahead == 0:  # If it's the same day, go to next week
                        if "next" in time_str.lower():
                            days_ahead = 7
                        elif now.hour >= 12:  # Past noon, probably means next week
                            days_ahead = 7
                    
                    # Default time is 9 AM
                    target_date = now + timedelta(days=days_ahead)
                    target_time = "9:00 AM"
                    
                    # Try to extract a time if specified
                    if "at" in time_str:
                        time_part = time_str.split("at")[-1].strip()
                        time_part = time_part.replace("am", " AM").replace("pm", " PM")
                        
                        # Try different time formats
                        time_formats = ["%I:%M %p", "%I:%M%p", "%I %p", "%H:%M"]
                        for fmt in time_formats:
                            try:
                                parsed_time = datetime.strptime(time_part, fmt)
                                target_time = parsed_time.strftime("%H:%M")
                                break
                            except ValueError:
                                continue
                    
                    # Parse the time part
                    try:
                        hour, minute = map(int, target_time.split(":")[:2])
                        target_dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except ValueError:
                        pass
            
            # If we successfully parsed the time
            if target_dt:
                # Ensure the time is in the future
                if target_dt <= now:
                    embed = self._create_embed(
                        "Invalid Time", 
                        "The time you specified appears to be in the past. Please choose a future time.",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Store in UTC
                utc_dt = target_dt.astimezone(pytz.UTC)
                trigger_time = utc_dt.timestamp()
                
                # Save the reminder
                self.reminders[trigger_time] = (interaction.user.id, reminder_text, user_timezone)
                self._save_reminders()
                
                # Format for display
                readable_time = target_dt.strftime("%A, %B %d at %I:%M %p")
                time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
                
                # Log and create response
                logger.info(f"Natural language reminder set - User: {interaction.user.id}, Time: '{time_str}' parsed as {target_dt}")
                
                embed = self._create_embed(
                    "Reminder Set ✅",
                    f"Your reminder has been set for **{readable_time}** ({time_until}).\n\n"
                    f"**Reminder:** {reminder_text}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # If we couldn't parse the time, show the modal
                await self._show_reminder_modal(interaction, reminder_text, user_timezone)
        except Exception as e:
            logger.error(f"Error processing natural language time: {e}", exc_info=True)
            # If there's an error, fall back to the date picker modal
            await self._show_reminder_modal(interaction, reminder_text, user_timezone)
    
    async def _show_reminder_modal(self, interaction, reminder_text, user_timezone):
        """Show the reminder modal with improved defaults"""
        # Get user's timezone
        user_timezone = self.get_user_timezone(interaction.user.id)
        
        # Create and send modal directly
        modal = ReminderModal(self, user_timezone)
        modal.reminder_text.default = reminder_text
        
        # Get the user's local timezone
        user_tz = pytz.timezone(user_timezone)
        
        # Pre-populate with tomorrow's date in user's timezone
        tomorrow = datetime.now(user_tz) + timedelta(days=1)
        modal.reminder_date.default = tomorrow.strftime("%Y-%m-%d")
        
        # Pre-populate with current time in user's timezone
        modal.reminder_time.default = datetime.now(user_tz).strftime("%H:%M")
        
        await interaction.response.send_modal(modal)

    @reminder.command(name="list", description="List all your upcoming reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        logger.info(f"User {interaction.user.id} listing reminders")
        
        user_id = interaction.user.id
        user_timezone = self.get_user_timezone(user_id)
        local_tz = pytz.timezone(user_timezone)
        
        user_reminders = [
            (ts, msg, tz) for ts, (uid, msg, tz) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            embed = self._create_embed(
                "No Reminders",
                "You have no upcoming reminders.",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Sort reminders by time
        user_reminders.sort(key=lambda x: x[0])
        
        # Format the output
        lines = []
        for ts, msg, _ in user_reminders:
            # Convert UTC timestamp to user's timezone
            utc_dt = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)
            local_dt = utc_dt.astimezone(local_tz)
            readable_time = local_dt.strftime("%A, %B %d at %I:%M %p")
            time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
            lines.append(f"⏰ **{readable_time}** ({time_until})\n> {msg}")
        
        # Create embed for better formatting
        embed = self._create_embed(
            "Your Reminders",
            f"You have {len(user_reminders)} upcoming reminder{'s' if len(user_reminders) != 1 else ''} (Timezone: {user_timezone})",
            color=discord.Color.blue()
        )
        
        # Split into fields if there are many reminders
        if len(user_reminders) <= 5:
            embed.description += ":\n\n" + "\n\n".join(lines)
        else:
            embed.description += f". Here are your next 5 reminders:"
            for i, line in enumerate(lines[:5]):
                embed.add_field(
                    name=f"Reminder #{i+1}",
                    value=line,
                    inline=False
                )
            if len(lines) > 5:
                embed.set_footer(text=f"+ {len(lines) - 5} more reminders. Use /reminder list_all to see all.")
        
        # Make this response ephemeral so only the user can see it
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reminder.command(name="cancel", description="Cancel a reminder using an interactive menu")
    async def cancel_reminder_menu(self, interaction: discord.Interaction):
        """Cancel a reminder using an interactive button menu"""
        logger.info(f"User {interaction.user.id} opening cancel reminder menu")
        
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg, _) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id} to cancel")
            embed = self._create_embed(
                "No Reminders",
                "You have no reminders to cancel.",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        user_timezone = self.get_user_timezone(user_id)
        
        embed = self._create_embed(
            "Cancel a Reminder",
            f"Select a reminder from below to cancel it (Timezone: {user_timezone}):",
            color=discord.Color.gold()
        )
        view = CancelReminderView(self, user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reminder.command(name="clear", description="Clear all your reminders")
    async def clear_all_reminders(self, interaction: discord.Interaction):
        """Clear all reminders for a user"""
        logger.info(f"User {interaction.user.id} clearing all reminders")
        
        user_id = interaction.user.id
        user_reminders = [
            ts for ts, (uid, _, _) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id} to clear")
            embed = self._create_embed(
                "No Reminders",
                "You have no reminders to clear.",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Confirmation view
        class ConfirmView(ui.View):
            def __init__(self, cog, user_reminders):
                super().__init__(timeout=60)
                self.cog = cog
                self.user_reminders = user_reminders
                
            @ui.button(label="Yes, clear all", style=discord.ButtonStyle.danger)
            async def confirm(self, confirm_interaction: discord.Interaction, button: ui.Button):
                if confirm_interaction.user.id != interaction.user.id:
                    embed = self.cog._create_embed(
                        "Access Denied",
                        "This isn't your confirmation dialog!",
                        color=discord.Color.red()
                    )
                    await confirm_interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
                for ts in self.user_reminders:
                    self.cog.reminders.pop(ts, None)
                self.cog._save_reminders()
                
                logger.info(f"User {interaction.user.id} cleared {len(self.user_reminders)} reminders")
                embed = self.cog._create_embed(
                    "Reminders Cleared",
                    f"✅ Successfully cleared {len(self.user_reminders)} reminders.",
                    color=discord.Color.green()
                )
                await confirm_interaction.response.edit_message(embed=embed, view=None)
                
            @ui.button(label="No, keep my reminders", style=discord.ButtonStyle.secondary)
            async def cancel(self, cancel_interaction: discord.Interaction, button: ui.Button):
                if cancel_interaction.user.id != interaction.user.id:
                    embed = self.cog._create_embed(
                        "Access Denied",
                        "This isn't your confirmation dialog!",
                        color=discord.Color.red()
                    )
                    await cancel_interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                    
                embed = self.cog._create_embed(
                    "Operation Cancelled",
                    "Operation cancelled. Your reminders are safe.",
                    color=discord.Color.blue()
                )
                await cancel_interaction.response.edit_message(embed=embed, view=None)
        
        embed = self._create_embed(
            "Confirm Clear All",
            f"⚠️ Are you sure you want to clear all {len(user_reminders)} reminders? This cannot be undone.",
            color=discord.Color.red()
        )
        view = ConfirmView(self, user_reminders)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reminder.command(name="next", description="Show your next upcoming reminder")
    async def next_reminder(self, interaction: discord.Interaction):
        """Show the next upcoming reminder"""
        logger.info(f"User {interaction.user.id} checking next reminder")
        
        user_id = interaction.user.id
        user_timezone = self.get_user_timezone(user_id)
        local_tz = pytz.timezone(user_timezone)
        
        user_reminders = [
            (ts, msg, tz) for ts, (uid, msg, tz) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            embed = self._create_embed(
                "No Reminders",
                "You have no upcoming reminders.",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Get the earliest reminder
        next_reminder = min(user_reminders, key=lambda x: x[0])
        ts, msg, _ = next_reminder
        
        # Convert UTC time to user's timezone
        utc_dt = datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.UTC)
        local_dt = utc_dt.astimezone(local_tz)
        readable_time = local_dt.strftime("%A, %B %d at %I:%M %p")
        time_until = self._format_time_until(utc_dt.replace(tzinfo=None))
        
        embed = self._create_embed(
            "Your Next Reminder ⏰",
            f"**{readable_time}** ({time_until})\n\n> {msg}",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    timezone = app_commands.Group(name="timezone", description="Manage your timezone settings", parent=reminder)
    
    @timezone.command(name="set", description="Set your timezone")
    async def set_timezone(self, interaction: discord.Interaction):
        """Set your timezone preferences using a dropdown menu"""
        logger.info(f"User {interaction.user.id} is setting their timezone")
        
        current_tz = self.get_user_timezone(interaction.user.id)
        
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
        
        user_timezone = self.get_user_timezone(interaction.user.id)
        
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
        logger.info("Reminder Cog unloading, saving reminders...")
        if self.task:
            self.task.cancel()
        self._save_reminders()
        self._save_user_timezones()

async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
    logger.info("Reminders cog setup complete")