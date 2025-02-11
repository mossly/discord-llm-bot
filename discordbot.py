import os
import asyncio
import logging
import time
from datetime import datetime

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logging.info(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        logging.info(f"Bot is in server: {guild.name} (id: {guild.id})")
    # Force a sync of the slash commands with Discord
    await bot.tree.sync()

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