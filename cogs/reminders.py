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
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Combine date and time inputs
            date_str = self.reminder_date.value
            time_str = self.reminder_time.value
            datetime_str = f"{date_str} {time_str}:00"
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
            
            # Check if the reminder is for the past
            now = time.time()
            if trigger_time <= now:
                logger.warning(f"User {interaction.user.id} attempted to set a reminder for the past: {datetime_str} (Now: {datetime.now()})")
                return await interaction.response.send_message(
                    "You can't set reminders for the past! Please choose a future time.",
                    ephemeral=True
                )
            
            # Check rate limiting for this user
            user_reminders = [r for t, (uid, r) in self.cog.reminders.items() if uid == interaction.user.id]
            if len(user_reminders) >= MAX_REMINDERS_PER_USER:
                logger.warning(f"User {interaction.user.id} hit max reminders limit ({MAX_REMINDERS_PER_USER})")
                return await interaction.response.send_message(
                    f"You already have {MAX_REMINDERS_PER_USER} reminders set. Please remove some before adding more.",
                    ephemeral=True
                )
            
            # Check if there's already a reminder at this exact time for this user
            if trigger_time in self.cog.reminders and self.cog.reminders[trigger_time][0] == interaction.user.id:
                logger.warning(f"User {interaction.user.id} attempted to set duplicate reminder at {datetime_str}")
                return await interaction.response.send_message(
                    "You already have a reminder set for this exact time. Please choose a different time.",
                    ephemeral=True
                )
            
            # All checks passed, add the reminder
            self.cog.reminders[trigger_time] = (interaction.user.id, self.reminder_text.value)
            self.cog._save_reminders()
            
            readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            time_until = self.cog._format_time_until(dt)
            
            logger.info(f"Reminder set - User: {interaction.user.id}, Current time: {datetime.now()}, Reminder time: {readable_time}, Text: '{self.reminder_text.value}'")
            
            await interaction.response.send_message(
                f"✅ Reminder set for **{readable_time}** UTC ({time_until} from now).\n"
                f"**Reminder:** {self.reminder_text.value}\n\n"
                f"I'll send you a DM when it's time!",
                ephemeral=True
            )
        except ValueError as e:
            logger.error(f"Date parsing error: {e} for input date={self.reminder_date.value}, time={self.reminder_time.value}")
            await interaction.response.send_message(
                "Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time.",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Error in ReminderModal: {error}", exc_info=True)
        await interaction.response.send_message(
            "An error occurred while processing your reminder.",
            ephemeral=True
        )

class SelectTimeView(ui.View):
    def __init__(self, cog, reminder_text, *, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.reminder_text = reminder_text
        
    @ui.button(label="Select Date & Time", style=discord.ButtonStyle.primary)
    async def select_time(self, interaction: discord.Interaction, button: ui.Button):
        modal = ReminderModal(self.cog)
        modal.reminder_text.default = self.reminder_text
        
        # Pre-populate with tomorrow's date
        tomorrow = datetime.now() + timedelta(days=1)
        modal.reminder_date.default = tomorrow.strftime("%Y-%m-%d")
        
        # Pre-populate with current time
        modal.reminder_time.default = datetime.now().strftime("%H:%M")
        
        await interaction.response.send_modal(modal)

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
        
        # Get user's reminders
        user_reminders = sorted(
            [(ts, msg) for ts, (uid, msg) in self.cog.reminders.items() if uid == self.user_id],
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
            ts, msg = user_reminders[i]
            dt = datetime.utcfromtimestamp(ts)
            time_str = dt.strftime("%Y-%m-%d %H:%M")
            
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
                await interaction.response.send_message("This isn't your reminder menu!", ephemeral=True)
                return
            
            self.cog.reminders.pop(timestamp, None)
            self.cog._save_reminders()
            
            # Re-render the view with updated buttons
            self._update_buttons()
            
            if not self.children:  # No buttons left
                await interaction.response.edit_message(content="You have no more reminders.", view=None)
            else:
                await interaction.response.edit_message(content="Reminder cancelled! Here are your remaining reminders:", view=self)
        
        return callback
    
    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your reminder menu!", ephemeral=True)
            return
            
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your reminder menu!", ephemeral=True)
            return
            
        user_reminders = [r for t, (uid, r) in self.cog.reminders.items() if uid == self.user_id]
        total_pages = (len(user_reminders) - 1) // self.reminders_per_page + 1
        
        self.page = min(total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)

class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders = {}
        self.task = None
        self.reminders_file = "reminders.json"
        self.dm_failed_users = set()  # Track users with failed DMs
        self._load_reminders()

    def _load_reminders(self):
        """Load reminders from disk"""
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r') as f:
                    # JSON can't store numbers as keys, so we convert back from strings
                    data = json.load(f)
                    self.reminders = {
                        float(ts): (int(uid), msg) 
                        for ts, (uid, msg) in data.items()
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
                str(ts): [uid, msg] 
                for ts, (uid, msg) in self.reminders.items()
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
        
        days, seconds = delta.days, delta.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 and not parts:  # Only include seconds if less than a minute
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            
        return ", ".join(parts)

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
                for trigger_time, (user_id, message) in self.reminders.items():
                    if trigger_time <= current_time:
                        to_trigger.append((trigger_time, user_id, message))
                
                # Process triggered reminders
                for trigger_time, user_id, message in to_trigger:
                    trigger_readable = datetime.utcfromtimestamp(trigger_time).strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"Triggering reminder - User: {user_id}, Current time: {now_readable}, Reminder time: {trigger_readable}, Text: '{message}'")
                    
                    try:
                        # Skip sending DM if user previously had DM failures
                        if user_id in self.dm_failed_users:
                            logger.warning(f"Skipping DM for user {user_id} (previous failures)")
                            continue
                            
                        user = await self.bot.fetch_user(user_id)
                        await user.send(f"⏰ **Reminder:** {message}")
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

    reminder = app_commands.Group(name="reminder", description="Manage your reminders")

    @reminder.command(name="add", description="Add a reminder using an interactive date/time picker")
    async def add_reminder(self, interaction: discord.Interaction, reminder_text: str):
        """Add a reminder using a date/time picker UI"""
        # Log the attempt
        logger.info(f"User {interaction.user.id} ({interaction.user.name}) is adding a reminder")
        
        # Check if user has too many reminders
        user_reminders = [r for t, (uid, r) in self.reminders.items() if uid == interaction.user.id]
        if len(user_reminders) >= MAX_REMINDERS_PER_USER:
            logger.warning(f"User {interaction.user.id} hit max reminders limit ({MAX_REMINDERS_PER_USER})")
            return await interaction.response.send_message(
                f"You already have {MAX_REMINDERS_PER_USER} reminders set. Please remove some before adding more.",
                ephemeral=True
            )
            
        view = SelectTimeView(self, reminder_text)
        await interaction.response.send_message(
            "Please select a date and time for your reminder:",
            view=view,
            ephemeral=True
        )

    @reminder.command(name="add_manual", description="Add a reminder with manual time input")
    async def add_reminder_manual(self, interaction: discord.Interaction, time_str: str, reminder_text: str):
        """Add a reminder with manual time input (YYYY-MM-DD HH:MM:SS)"""
        logger.info(f"User {interaction.user.id} is adding a manual reminder for time {time_str}")
        
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
            
            # Check if reminder is for the past
            now = time.time()
            if trigger_time <= now:
                logger.warning(f"User {interaction.user.id} attempted to set a reminder for the past: {time_str}")
                return await interaction.response.send_message(
                    "You can't set reminders for the past! Please choose a future time.",
                    ephemeral=True
                )
            
            # Check rate limiting
            user_reminders = [r for t, (uid, r) in self.reminders.items() if uid == interaction.user.id]
            if len(user_reminders) >= MAX_REMINDERS_PER_USER:
                logger.warning(f"User {interaction.user.id} hit max reminders limit ({MAX_REMINDERS_PER_USER})")
                return await interaction.response.send_message(
                    f"You already have {MAX_REMINDERS_PER_USER} reminders set. Please remove some before adding more.",
                    ephemeral=True
                )
            
            self.reminders[trigger_time] = (interaction.user.id, reminder_text)
            self._save_reminders()
            
            time_until = self._format_time_until(dt)
            logger.info(f"Reminder set - User: {interaction.user.id}, Current time: {datetime.now()}, Reminder time: {time_str}, Text: '{reminder_text}'")
            
            await interaction.response.send_message(
                f"✅ Reminder set for **{time_str}** UTC ({time_until} from now).\n"
                f"**Reminder:** {reminder_text}\n\n"
                f"I'll send you a DM when it's time!",
                ephemeral=True
            )
            
        except ValueError:
            logger.error(f"Invalid time format: {time_str} from user {interaction.user.id}")
            return await interaction.response.send_message(
                "Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)",
                ephemeral=True
            )

    @reminder.command(name="list", description="List all your upcoming reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        logger.info(f"User {interaction.user.id} listing reminders")
        
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            return await interaction.response.send_message("You have no upcoming reminders.", ephemeral=True)

        # Sort reminders by time
        user_reminders.sort(key=lambda x: x[0])
        
        # Format the output
        lines = []
        for ts, msg in user_reminders:
            dt = datetime.utcfromtimestamp(ts)
            readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            time_until = self._format_time_until(dt)
            lines.append(f"⏰ **{readable_time}** UTC ({time_until} from now)\n> {msg}")
        
        # Create embed for better formatting
        embed = discord.Embed(
            title="Your Reminders",
            description=f"You have {len(user_reminders)} upcoming reminder{'s' if len(user_reminders) != 1 else ''}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
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

    @reminder.command(name="list_all", description="List all your upcoming reminders in detail")
    async def list_all_reminders(self, interaction: discord.Interaction):
        logger.info(f"User {interaction.user.id} listing all reminders in detail")
        
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            return await interaction.response.send_message("You have no upcoming reminders.", ephemeral=True)

        # Sort reminders by time
        user_reminders.sort(key=lambda x: x[0])
        
        # Format the output
        lines = []
        for ts, msg in user_reminders:
            dt = datetime.utcfromtimestamp(ts)
            readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            time_until = self._format_time_until(dt)
            lines.append(f"⏰ **{readable_time}** UTC ({time_until} from now)\n> {msg}")
        
        # Split into chunks to avoid Discord's message limit
        chunks = []
        current_chunk = ["**All Your Reminders:**"]
        
        for line in lines:
            if len("\n\n".join(current_chunk + [line])) > 1900:  # Discord limit is 2000, leave some margin
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [line]
            else:
                current_chunk.append(line)
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        # Send the first message
        await interaction.response.send_message(chunks[0], ephemeral=True)
        
        # Send follow-up messages if needed
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)

    @reminder.command(name="cancel", description="Cancel a reminder using an interactive menu")
    async def cancel_reminder_menu(self, interaction: discord.Interaction):
        """Cancel a reminder using an interactive button menu"""
        logger.info(f"User {interaction.user.id} opening cancel reminder menu")
        
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id} to cancel")
            return await interaction.response.send_message("You have no reminders to cancel.", ephemeral=True)
        
        view = CancelReminderView(self, user_id)
        await interaction.response.send_message(
            "Select a reminder to cancel:",
            view=view,
            ephemeral=True
        )

    @reminder.command(name="cancel_manual", description="Cancel a reminder at a specific time")
    async def cancel_reminder_manual(self, interaction: discord.Interaction, time_str: str):
        """Manually cancel a reminder at a specific time"""
        logger.info(f"User {interaction.user.id} attempting to manually cancel reminder at {time_str}")
        
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            logger.warning(f"Invalid time format in cancel request: {time_str}")
            return await interaction.response.send_message(
                "Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)",
                ephemeral=True
            )

        entry = self.reminders.get(trigger_time)
        if entry and entry[0] == interaction.user.id:
            reminder_text = entry[1]
            self.reminders.pop(trigger_time)
            self._save_reminders()
            logger.info(f"User {interaction.user.id} cancelled reminder at {time_str}: '{reminder_text}'")
            return await interaction.response.send_message(f"Reminder cancelled: '{reminder_text}'")
        else:
            logger.info(f"No matching reminder found for user {interaction.user.id} at time {time_str}")
            return await interaction.response.send_message(
                "No matching reminder found for you at that time.",
                ephemeral=True
            )

    @reminder.command(name="clear_all", description="Clear all your reminders")
    async def clear_all_reminders(self, interaction: discord.Interaction):
        """Clear all reminders for a user"""
        logger.info(f"User {interaction.user.id} clearing all reminders")
        
        user_id = interaction.user.id
        user_reminders = [
            ts for ts, (uid, _) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id} to clear")
            return await interaction.response.send_message("You have no reminders to clear.", ephemeral=True)
        
        # Confirmation view
        class ConfirmView(ui.View):
            def __init__(self, cog, user_reminders):
                super().__init__(timeout=60)
                self.cog = cog
                self.user_reminders = user_reminders
                
            @ui.button(label="Yes, clear all", style=discord.ButtonStyle.danger)
            async def confirm(self, confirm_interaction: discord.Interaction, button: ui.Button):
                if confirm_interaction.user.id != interaction.user.id:
                    await confirm_interaction.response.send_message("This isn't your confirmation dialog!", ephemeral=True)
                    return
                    
                for ts in self.user_reminders:
                    self.cog.reminders.pop(ts, None)
                self.cog._save_reminders()
                
                logger.info(f"User {interaction.user.id} cleared {len(self.user_reminders)} reminders")
                await confirm_interaction.response.edit_message(
                    content=f"✅ Successfully cleared {len(self.user_reminders)} reminders.",
                    view=None
                )
                
            @ui.button(label="No, keep my reminders", style=discord.ButtonStyle.secondary)
            async def cancel(self, cancel_interaction: discord.Interaction, button: ui.Button):
                if cancel_interaction.user.id != interaction.user.id:
                    await cancel_interaction.response.send_message("This isn't your confirmation dialog!", ephemeral=True)
                    return
                    
                await cancel_interaction.response.edit_message(
                    content="Operation cancelled. Your reminders are safe.",
                    view=None
                )
        
        view = ConfirmView(self, user_reminders)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to clear all {len(user_reminders)} reminders? This cannot be undone.",
            view=view,
            ephemeral=True
        )

    @reminder.command(name="next", description="Show your next upcoming reminder")
    async def next_reminder(self, interaction: discord.Interaction):
        """Show the next upcoming reminder"""
        logger.info(f"User {interaction.user.id} checking next reminder")
        
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        
        if not user_reminders:
            logger.info(f"No reminders found for user {interaction.user.id}")
            return await interaction.response.send_message("You have no upcoming reminders.", ephemeral=True)
        
        # Get the earliest reminder
        next_reminder = min(user_reminders, key=lambda x: x[0])
        ts, msg = next_reminder
        
        dt = datetime.utcfromtimestamp(ts)
        readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        time_until = self._format_time_until(dt)
        
        embed = discord.Embed(
            title="Your Next Reminder",
            description=f"⏰ **{readable_time}** UTC\n({time_until} from now)\n\n> {msg}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_unload(self):
        logger.info("Reminder Cog unloading, saving reminders...")
        if self.task:
            self.task.cancel()
        self._save_reminders()

async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
    logger.info("Reminders cog setup complete")