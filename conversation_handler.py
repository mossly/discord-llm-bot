"""
Conversation handler for Discord thread interactions
Extracted from discordbot.py to improve maintainability and separation of concerns
"""

import asyncio
import logging
import discord
from utils.embed_utils import create_error_embed

logger = logging.getLogger(__name__)


class ConversationHandler:
    """Handles conversation flow in Discord threads"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def handle_thread_conversation(self, message: discord.Message):
        """Handle conversation in AI threads"""
        try:
            # Get AI commands cog
            ai_commands = self.bot.get_cog("AICommands")
            if not ai_commands:
                logger.error("AICommands cog not found")
                return
            
            # Extract model from the first bot message footer
            model_key = await self._detect_thread_model(message.channel)
            
            # Detect fun mode from thread history
            fun_mode = await self._detect_thread_fun_mode(message.channel)
            
            # Gather conversation history from thread
            conversation_history = await self._build_conversation_history(message.channel, message)
            
            # Build context and prompt
            context_text, current_prompt = self._build_context_and_prompt(
                conversation_history, message
            )
            
            # Log processing info
            logger.info(
                f"Processing thread message from {message.author.name} in thread {message.channel.name}"
            )
            logger.info(
                f"Using model: {model_key}, context messages: {len(conversation_history)}, "
                f"total prompt length: {len(context_text + current_prompt)}"
            )
            
            # Send thinking message
            thinking_msg = await message.reply("-# *Thinking...*")
            
            try:
                # Process the AI request
                full_prompt = self._combine_context_and_prompt(context_text, current_prompt)
                # Define allowed tools for regular AI threads (character_sheet excluded - RPG only)
                # Tool names must match the actual tool.name property values
                allowed_tools = [
                    "search_web", "get_contents", "search_conversations",
                    "search_discord_messages", "search_current_discord_messages",
                    "lookup_discord_users", "manage_reminders", "roll_dice",
                    "deep_research", "task_management"
                ]
                await ai_commands._process_ai_request(
                    prompt=full_prompt,
                    model_key=model_key,
                    reply_msg=message,
                    reply_user=message.author,
                    fun=fun_mode,  # Use detected fun mode
                    tool_calling=True,  # Enable tools by default in threads
                    allowed_tools=allowed_tools  # Exclude character_sheet from regular threads
                )
            finally:
                # Clean up thinking message
                try:
                    await thinking_msg.delete()
                except:
                    pass  # Ignore deletion errors
                
        except Exception as e:
            logger.error(f"Error handling thread conversation: {e}")
            # Send standardized error embed to thread
            error_embed = create_error_embed(f"Error processing message: {str(e)[:100]}...")
            await message.channel.send(embed=error_embed)
    
    async def _detect_thread_model(self, channel: discord.Thread) -> str:
        """Detect the model used in a thread from the first bot message"""
        model_key = None

        # Look through the first 50 messages to find bot's initial message
        async for msg in channel.history(limit=50, oldest_first=True):
            if msg.author == self.bot.user and msg.embeds and msg.embeds[0].footer:
                footer_text = msg.embeds[0].footer.text
                if footer_text:
                    first_line = footer_text.split('\n')[0].strip()
                    # Remove RPG Mode and Fun Mode suffixes if present
                    if " | RPG Mode" in first_line:
                        first_line = first_line.replace(" | RPG Mode", "")
                    if " | Fun Mode" in first_line:
                        first_line = first_line.replace(" | Fun Mode", "")
                    # Try to detect model from footer
                    from cogs.ai_commands import MODELS_CONFIG
                    for key, config in MODELS_CONFIG.items():
                        if (config.get("default_footer") == first_line or
                            config.get("name") == first_line):
                            model_key = key
                            break
                break

        # Fallback to default model if detection fails
        if not model_key:
            from cogs.ai_commands import DEFAULT_MODEL
            model_key = DEFAULT_MODEL

        return model_key
    
    async def _detect_thread_fun_mode(self, channel: discord.Thread) -> bool:
        """Detect if fun mode is used in a thread from bot message footers"""
        # Look through the first 20 messages to find bot messages with fun mode
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.author == self.bot.user and msg.embeds and msg.embeds[0].footer:
                footer_text = msg.embeds[0].footer.text
                if footer_text and "Fun Mode" in footer_text:
                    logger.info(f"Detected fun mode in thread from footer: {footer_text}")
                    return True
        
        logger.info("No fun mode detected in thread history")
        return False
    
    async def _build_conversation_history(self, channel: discord.Thread, current_message: discord.Message) -> list:
        """Build conversation history from thread messages"""
        conversation_history = []
        
        # Gather conversation history from thread (newest first, excluding current message)
        async for msg in channel.history(limit=50, before=current_message):
            if msg.author == self.bot.user:
                # Bot message - extract content from embed
                if msg.embeds and msg.embeds[0].description:
                    conversation_history.append(f"Assistant: {msg.embeds[0].description}")
            elif not msg.author.bot:
                # User message
                conversation_history.append(f"{msg.author.name}: {msg.content}")
        
        # Reverse to get chronological order (oldest first)
        conversation_history.reverse()
        return conversation_history
    
    def _build_context_and_prompt(self, conversation_history: list, message: discord.Message) -> tuple[str, str]:
        """Build context text and current prompt, handling length limits"""
        max_context_length = 4000  # Leave room for current message and system prompts
        
        # Separate system prompts from regular conversation messages
        system_prompts, regular_messages = self._separate_system_prompts(conversation_history)
        
        # Build context with system prompts first, then regular messages
        context_text = "\n".join(system_prompts + regular_messages)
        
        # If context is too long, trim regular messages while preserving system prompts
        while len(context_text) > max_context_length and regular_messages:
            regular_messages.pop(0)  # Remove oldest regular message, keep system prompts
            context_text = "\n".join(system_prompts + regular_messages)
        
        # Build current prompt
        current_prompt = f"{message.author.name}: {message.content}"
        
        return context_text, current_prompt
    
    def _separate_system_prompts(self, conversation_history: list) -> tuple[list, list]:
        """Separate system prompts from regular conversation messages"""
        system_prompts = []
        regular_messages = []
        
        for msg in conversation_history:
            # Identify system prompts - these are typically the first assistant messages 
            # or messages containing system-like content
            if (msg.startswith("Assistant:") and 
                (len(regular_messages) == 0 or  # First assistant message is likely system prompt
                 any(keyword in msg.lower() for keyword in [
                     "current date and time:", "you are", "system", "instructions",
                     "server id:", "channel id:", "discord context"
                 ]))):
                system_prompts.append(msg)
            else:
                regular_messages.append(msg)
        
        return system_prompts, regular_messages
    
    def _combine_context_and_prompt(self, context_text: str, current_prompt: str) -> str:
        """Combine context and current prompt into final prompt"""
        if context_text:
            return f"Previous conversation:\n{context_text}\n\nCurrent message:\n{current_prompt}"
        else:
            return current_prompt


async def is_ai_conversation_thread(bot, channel: discord.Thread) -> bool:
    """Check if this is an AI conversation thread"""
    if not isinstance(channel, discord.Thread):
        return False

    try:
        # Check if the first message is from our bot
        first_message = None
        async for msg in channel.history(limit=1, oldest_first=True):
            first_message = msg
            break

        return first_message and first_message.author == bot.user

    except Exception as e:
        logger.error(f"Error checking if thread is AI conversation: {e}")
        return False


async def is_rpg_conversation_thread(bot, channel: discord.Thread) -> bool:
    """Check if this is an RPG conversation thread (has 'RPG Mode' in first message footer)"""
    if not isinstance(channel, discord.Thread):
        return False

    try:
        async for msg in channel.history(limit=1, oldest_first=True):
            if msg.author == bot.user and msg.embeds:
                footer_text = msg.embeds[0].footer.text if msg.embeds[0].footer else ""
                return "RPG Mode" in footer_text
        return False
    except Exception as e:
        logger.error(f"Error checking if thread is RPG conversation: {e}")
        return False