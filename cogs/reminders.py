import asyncio
import time
import logging
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders = {}
        self.task = None

    async def cog_load(self):
        self.task = asyncio.create_task(self.reminder_loop())

    async def reminder_loop(self):
        while True:
            now = time.time()
            to_remove = []
            for trigger_time, (user_id, message) in self.reminders.items():
                if trigger_time <= now:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        logger.info(f"Sending reminder to {user}: {message}")
                        await user.send(f"Reminder: {message}")
                    except Exception as e:
                        logger.error(f"Failed to send reminder for user {user_id}: {e}")
                    to_remove.append(trigger_time)
            for trigger_time in to_remove:
                self.reminders.pop(trigger_time, None)
            await asyncio.sleep(1)

    reminder = app_commands.Group(name="reminder", description="Manage your reminders")

    @reminder.command(name="add", description="Add a reminder at a specific time")
    async def add_reminder(self, interaction: discord.Interaction, time_str: str, reminder_text: str):
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await interaction.response.send_message("Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)", ephemeral=True)

        self.reminders[trigger_time] = (interaction.user.id, reminder_text)
        await interaction.response.send_message(f"Reminder '{reminder_text}' set for {time_str} UTC.")

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
        await interaction.response.send_message("\n".join(lines))

    @reminder.command(name="cancel", description="Cancel a reminder at a specific time")
    async def cancel_reminder(self, interaction: discord.Interaction, time_str: str):
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await interaction.response.send_message("Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)", ephemeral=True)

        entry = self.reminders.get(trigger_time)
        if entry and entry[0] == interaction.user.id:
            self.reminders.pop(trigger_time)
            return await interaction.response.send_message("Reminder cancelled.")
        else:
            return await interaction.response.send_message("No matching reminder found for you at that time.", ephemeral=True)

    async def cog_unload(self):
        if self.task:
            self.task.cancel()

async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))