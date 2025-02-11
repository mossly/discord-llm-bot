import os
import asyncio
import logging
import time
from datetime import datetime

import discord
from discord.ext import commands

# Configure logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Set up the bot with the desired command prefix and intents.
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# (Optional) Reminder functionality.
# Place any scheduled reminders here. For example:
reminders = [
    # Example: ('2024-04-17 03:50:00', 'Take out the garbage'),
]
reminders2 = {datetime.fromisoformat(rem[0]).timestamp(): rem[1] for rem in reminders}

def convert_to_readable(timestamp):
    """Convert a Unix timestamp to a human‐readable date string."""
    return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

async def background():
    """Periodically checks for due reminders and sends a DM to the user."""
    reminder_times = list(reminders2.keys())
    while True:
        now = time.time()
        for t in reminder_times:
            if t in reminders2 and t < now:
                try:
                    # Replace with your own user ID.
                    user = await bot.fetch_user("195485849952059392")
                    logging.info(f"Sending reminder to {user}: {reminders2[t]}")
                    await user.send(f"Reminder: {reminders2[t]}")
                except Exception as e:
                    logging.error(f"Failed to send reminder: {e}")
                del reminders2[t]
                reminder_times.remove(t)
                break
        await asyncio.sleep(1)

@bot.event
async def on_ready():
    """Called once the bot has connected to Discord."""
    logging.info(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        logging.info(f"Bot is in server: {guild.name} (id: {guild.id})")
    # Start the background reminder task.
    bot.loop.create_task(background())

async def load_cogs():
    """
    Dynamically load all Python modules (cogs) in the 'cogs' directory.
    Each cog is responsible for its own commands and functionality.
    """
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            logging.info(f"Loaded cog: {filename}")

async def main():
    await load_cogs()
    await bot.start(os.getenv("BOT_API_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())