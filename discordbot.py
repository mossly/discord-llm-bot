import os
import asyncio
import logging
import discord
from discord.ext import commands
from conversation_handler import ConversationHandler, is_ai_conversation_thread, is_rpg_conversation_thread
from config_manager import config
from utils.conversation_db import conversation_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for user lookup and username resolution
bot = commands.Bot(command_prefix=config.get('command_prefix', '!'), intents=intents)

# Initialize conversation handler
conversation_handler = ConversationHandler(bot)

@bot.event
async def on_ready():
    logging.info(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        logging.info(f"Bot is in server: {guild.name} (id: {guild.id})")

    # Initialize conversation database
    try:
        await conversation_db.initialize()
        bot.conversation_db = conversation_db
        logging.info("Conversation database initialized")
    except Exception as e:
        logging.error(f"Failed to initialize conversation database: {e}")

    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s) to Discord")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

@bot.command(name="sync")
@commands.is_owner()
async def sync_commands(ctx, scope: str = None):
    """Manually sync slash commands with Discord

    Usage:
        !sync        - Sync to current guild (instant) or global if in DMs
        !sync global - Sync globally (can take up to 1 hour)
    """
    try:
        if scope == "global" or ctx.guild is None:
            synced = await bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} command(s) globally")
            logging.info(f"Manual sync: {len(synced)} command(s) synced globally")
        else:
            synced = await bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"Synced {len(synced)} command(s) to this server (instant)")
            logging.info(f"Manual sync: {len(synced)} command(s) synced to guild {ctx.guild.id}")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")
        logging.error(f"Manual sync failed: {e}")

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Check RPG thread first (more specific check)
    if await is_rpg_conversation_thread(bot, message.channel):
        rpg_cog = bot.get_cog("RPG")
        if rpg_cog:
            await rpg_cog.handle_rpg_thread_conversation(message)
    # Then check regular AI conversation threads
    elif await is_ai_conversation_thread(bot, message.channel):
        await conversation_handler.handle_thread_conversation(message)

    # Process prefix commands (like !sync)
    await bot.process_commands(message)


async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            logging.info(f"Loaded cog: {filename}")

async def main():
    # Validate configuration before starting
    config_issues = config.validate_configuration()
    if config_issues:
        for issue in config_issues:
            logging.error(f"Configuration issue: {issue}")
        raise RuntimeError("Configuration validation failed")
    
    await load_cogs()
    await bot.start(config.get_required('bot_token'))

if __name__ == "__main__":
    asyncio.run(main())