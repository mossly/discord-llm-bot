import asyncio
import time
import logging
import json
import os
from datetime import datetime
import discord
from discord import app_commands, ui
from discord.ext import commands

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
            
            self.cog.reminders[trigger_time] = (interaction.user.id, self.reminder_text.value)
            self.cog._save_reminders()
            
            readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            await interaction.response.send_message(
                f"Reminder '{self.reminder_text.value}' set for {readable_time} UTC. I'll DM you when it's time!"
            )
        except ValueError:
            await interaction.response.send_message(
                "Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time.",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            "An error occurred while processing your reminder.",
            ephemeral=True
        )
        logger.error(f"Error in ReminderModal: {error}")

class SelectTimeView(ui.View):
    def __init__(self, cog, reminder_text, *, timeout=180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.reminder_text = reminder_text
        
    @ui.button(label="Select Date & Time", style=discord.ButtonStyle.primary)
    async def select_time(self, interaction: discord.Interaction, button: ui.Button):
        modal = ReminderModal(self.cog)
        modal.reminder_text.default = self.reminder_text
        await interaction.response.send_modal(modal)

class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders = {}
        self.task = None
        self.reminders_file = "reminders.json"
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
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}")
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
            logger.error(f"Failed to save reminders: {e}")

    async def cog_load(self):
        self.task = asyncio.create_task(self.reminder_loop())

    async def reminder_loop(self):
        while True:
            now = time.time()
            to_remove = []
            save_needed = False
            
            for trigger_time, (user_id, message) in self.reminders.items():
                if trigger_time <= now:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        logger.info(f"Sending reminder to {user}: {message}")
                        await user.send(f"Reminder: {message}")
                    except Exception as e:
                        logger.error(f"Failed to send reminder for user {user_id}: {e}")
                    to_remove.append(trigger_time)
                    save_needed = True
                    
            for trigger_time in to_remove:
                self.reminders.pop(trigger_time, None)
                
            if save_needed:
                self._save_reminders()
                
            await asyncio.sleep(1)

    reminder = app_commands.Group(name="reminder", description="Manage your reminders")

    @reminder.command(name="add", description="Add a reminder")
    async def add_reminder(self, interaction: discord.Interaction, reminder_text: str):
        """Add a reminder using a date/time picker UI"""
        view = SelectTimeView(self, reminder_text)
        await interaction.response.send_message(
            "Please select a date and time for your reminder:",
            view=view,
            ephemeral=True
        )

    @reminder.command(name="add_manual", description="Add a reminder with manual time input")
    async def add_reminder_manual(self, interaction: discord.Interaction, time_str: str, reminder_text: str):
        """Add a reminder with manual time input (YYYY-MM-DD HH:MM:SS)"""
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await interaction.response.send_message(
                "Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)",
                ephemeral=True
            )

        self.reminders[trigger_time] = (interaction.user.id, reminder_text)
        self._save_reminders()  # Save after adding a reminder
        await interaction.response.send_message(
            f"Reminder '{reminder_text}' set for {time_str} UTC. I'll DM you when it's time!"
        )

    @reminder.command(name="list", description="List all your upcoming reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        if not user_reminders:
            return await interaction.response.send_message("You have no upcoming reminders.", ephemeral=True)

        lines = []
        for ts, msg in sorted(user_reminders, key=lambda x: x[0]):
            readable_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{readable_time} UTC - {msg}")
        
        # Make this response ephemeral so only the user can see it
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @reminder.command(name="cancel", description="Cancel a reminder at a specific time")
    async def cancel_reminder(self, interaction: discord.Interaction, time_str: str):
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await interaction.response.send_message(
                "Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)",
                ephemeral=True
            )

        entry = self.reminders.get(trigger_time)
        if entry and entry[0] == interaction.user.id:
            self.reminders.pop(trigger_time)
            self._save_reminders()  # Save after canceling a reminder
            return await interaction.response.send_message("Reminder cancelled.")
        else:
            return await interaction.response.send_message(
                "No matching reminder found for you at that time.",
                ephemeral=True
            )

    async def cog_unload(self):
        if self.task:
            self.task.cancel()
        self._save_reminders()  # Save reminders when the cog is unloaded

async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))