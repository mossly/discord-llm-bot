import asyncio
import time
import logging
from datetime import datetime

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Maintain reminders in a dictionary:
        # key: trigger timestamp (seconds since epoch)
        # value: tuple (user_id, reminder_message)
        self.reminders = {}
        self.task = None  # Will be created in the async hook

    async def cog_load(self):
        # Create the background task once the cog is loaded and the event loop is available.
        self.task = asyncio.create_task(self.reminder_loop())

    async def reminder_loop(self):
        """Background loop that checks for due reminders every second."""
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

    @commands.command(name="addreminder")
    async def add_reminder(self, ctx: commands.Context, time_str: str, *, reminder_text: str):
        """
        Add a reminder.
        Usage: !addreminder YYYY-MM-DD HH:MM:SS <reminder text>
        Time is interpreted in UTC.
        """
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await ctx.send("Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)")

        self.reminders[trigger_time] = (ctx.author.id, reminder_text)
        await ctx.send(f"Reminder '{reminder_text}' set for {time_str} UTC.")

    @commands.command(name="listreminders")
    async def list_reminders(self, ctx: commands.Context):
        """
        List all upcoming reminders for you.
        """
        user_id = ctx.author.id
        user_reminders = [
            (ts, msg) for ts, (uid, msg) in self.reminders.items() if uid == user_id
        ]
        if not user_reminders:
            return await ctx.send("You have no upcoming reminders.")

        lines = []
        for ts, msg in sorted(user_reminders, key=lambda x: x[0]):
            readable_time = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{readable_time} UTC - {msg}")
        await ctx.send("\n".join(lines))

    @commands.command(name="cancelreminder")
    async def cancel_reminder(self, ctx: commands.Context, time_str: str):
        """
        Cancel a reminder you set.
        Usage: !cancelreminder YYYY-MM-DD HH:MM:SS
        The time must match the one you received when adding/listing the reminder (UTC).
        """
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            trigger_time = dt.timestamp()
        except ValueError:
            return await ctx.send("Time format incorrect. Please use: YYYY-MM-DD HH:MM:SS (UTC)")

        entry = self.reminders.get(trigger_time)
        if entry and entry[0] == ctx.author.id:
            self.reminders.pop(trigger_time)
            return await ctx.send("Reminder cancelled.")
        else:
            return await ctx.send("No matching reminder found for you at that time.")

    async def cog_unload(self):
        if self.task:
            self.task.cancel()

async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))