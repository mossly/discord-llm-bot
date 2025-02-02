from discord.ext import commands, tasks
import time
from datetime import datetime

class ReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Set up your reminders – for example, using a dictionary with Unix timestamps as keys.
        self.reminders = {
            # Example usage:
            # datetime.fromisoformat("2024-04-17 03:50:00").timestamp(): "Take out the garbage"
        }
        # Start the background loop.
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(seconds=1)
    async def check_reminders(self):
        now = time.time()
        to_remove = []
        for timestamp in list(self.reminders.keys()):
            if timestamp < now:
                try:
                    # Replace the ID with the actual recipient's user ID.
                    user = await self.bot.fetch_user(195485849952059392)
                    await user.send(f"Reminder: {self.reminders[timestamp]}")
                except Exception as e:
                    print(f"Failed to send reminder: {e}")
                to_remove.append(timestamp)
        for timestamp in to_remove:
            del self.reminders[timestamp]

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

# The setup function must be asynchronous.
async def setup(bot: commands.Bot):
    await bot.add_cog(ReminderCog(bot))