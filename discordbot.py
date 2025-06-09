import os
import asyncio
import logging
import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logging.info(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        logging.info(f"Bot is in server: {guild.name} (id: {guild.id})")
    await bot.tree.sync()

async def load_cogs():
    # Skip utility modules that are not cogs
    skip_files = {"model_cache.py"}
    
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename not in skip_files:
            await bot.load_extension(f"cogs.{filename[:-3]}")
            logging.info(f"Loaded cog: {filename}")

async def main():
    await load_cogs()
    await bot.start(os.getenv("BOT_API_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())