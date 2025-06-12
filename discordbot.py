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

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Only handle messages in threads
    if not isinstance(message.channel, discord.Thread):
        return
    
    # Check if this is an AI conversation thread
    # (thread where the first message is from our bot)
    try:
        first_message = None
        async for msg in message.channel.history(limit=1, oldest_first=True):
            first_message = msg
            break
        
        if not first_message or first_message.author != bot.user:
            return
        
        # This is an AI thread, respond to the user's message
        await handle_thread_conversation(message)
        
    except Exception as e:
        logging.error(f"Error in thread conversation handler: {e}")

async def handle_thread_conversation(message):
    """Handle conversation in AI threads"""
    try:
        # Get AI commands cog
        ai_commands = bot.get_cog("AICommands")
        if not ai_commands:
            return
        
        # Extract model from the first bot message footer
        model_key = None
        async for msg in message.channel.history(limit=50, oldest_first=True):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].footer:
                footer_text = msg.embeds[0].footer.text
                if footer_text:
                    first_line = footer_text.split('\n')[0].strip()
                    # Try to detect model from footer
                    from cogs.ai_commands import MODELS_CONFIG
                    for key, config in MODELS_CONFIG.items():
                        if config.get("default_footer") == first_line or config.get("name") == first_line:
                            model_key = key
                            break
                break
        
        # Fallback to default model if detection fails
        if not model_key:
            from cogs.ai_commands import DEFAULT_MODEL
            model_key = DEFAULT_MODEL
        
        # Gather conversation history from thread (newest first, excluding current message)
        conversation_history = []
        async for msg in message.channel.history(limit=50, before=message):
            if msg.author == bot.user:
                # Bot message - extract content from embed
                if msg.embeds and msg.embeds[0].description:
                    conversation_history.append(f"Assistant: {msg.embeds[0].description}")
            elif not msg.author.bot:
                # User message
                conversation_history.append(f"{msg.author.name}: {msg.content}")
        
        # Reverse to get chronological order (oldest first)
        conversation_history.reverse()
        
        # Limit context length - keep recent messages, trim from beginning if needed
        max_context_length = 4000  # Leave room for current message and system prompts
        context_text = "\n".join(conversation_history)
        
        # If context is too long, trim from the beginning
        while len(context_text) > max_context_length and conversation_history:
            conversation_history.pop(0)  # Remove oldest message
            context_text = "\n".join(conversation_history)
        
        # Build final prompt
        current_prompt = f"{message.author.name}: {message.content}"
        
        if conversation_history:
            full_prompt = f"Previous conversation:\n{context_text}\n\nCurrent message:\n{current_prompt}"
        else:
            full_prompt = current_prompt
        
        # Process the AI request using the same model and in the thread
        logging.info(f"Processing thread message from {message.author.name} in thread {message.channel.name}")
        logging.info(f"Using model: {model_key}, context messages: {len(conversation_history)}, total prompt length: {len(full_prompt)}")
        
        # Send thinking message
        thinking_msg = await message.reply("🤖 Thinking...")
        
        try:
            await ai_commands._process_ai_request(
                prompt=full_prompt,
                model_key=model_key,
                reply_msg=message,
                reply_user=message.author,
                tool_calling=True  # Enable tools by default in threads
            )
        finally:
            # Clean up thinking message
            try:
                await thinking_msg.delete()
            except:
                pass  # Ignore deletion errors
        
    except Exception as e:
        logging.error(f"Error handling thread conversation: {e}")
        # Send simple error message to thread
        await message.channel.send(f"❌ Error processing message: {str(e)[:100]}...")

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            logging.info(f"Loaded cog: {filename}")

async def main():
    await load_cogs()
    await bot.start(os.getenv("BOT_API_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())