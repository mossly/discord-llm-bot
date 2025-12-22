"""
RPG Cog - Provides RPG character sheet management functionality
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Optional
from enum import Enum

from utils.character_sheet_manager import CharacterSheetManager
from utils.embed_utils import create_error_embed, send_embed
from config_manager import config

logger = logging.getLogger(__name__)

# RPG System Prompt (base - will be combined with fun prompt if enabled)
RPG_SYSTEM_PROMPT = """You are a Game Master running a tabletop RPG session. Create immersive narratives, voice NPCs distinctively, and manage game mechanics fairly.

TOOLS AVAILABLE:
- character_sheet: View/modify player stats (HP, MP, XP, Level, Gold, inventory, attributes)
- roll_dice: Roll dice for checks, combat, saves, random events

RULES:
1. ALWAYS use character_sheet to track damage, healing, XP gains, loot, level ups
2. ALWAYS use roll_dice for random outcomes - never fabricate dice results
3. Narrate results dramatically after each roll
4. Keep challenges appropriate to the character's level
5. Create memorable NPCs with distinct personalities
6. Describe scenes vividly to immerse the player
7. When combat occurs, track HP changes with character_sheet

The player's current character stats will be provided in context. Use them to inform your narrative and ensure mechanical consistency."""

# RPG allowed tools
RPG_ALLOWED_TOOLS = ["character_sheet", "roll_dice"]


class RPG(commands.Cog):
    """Cog for RPG character sheet management"""

    def __init__(self, bot):
        self.bot = bot
        self.character_manager = CharacterSheetManager()

    async def cog_load(self):
        """Initialize the character sheet manager when the cog loads"""
        await self.character_manager.initialize()

        # Defer tool registration to ensure ToolCalling cog is loaded
        asyncio.create_task(self._register_tools_when_ready())

        logger.info("RPG cog loaded successfully")

    async def _register_tools_when_ready(self):
        """Register tools after a short delay to ensure all cogs are loaded"""
        await asyncio.sleep(0.5)  # Short delay to ensure all cogs are loaded

        tool_calling_cog = self.bot.get_cog("ToolCalling")
        if tool_calling_cog:
            tool_calling_cog.register_character_sheet_tool(self.character_manager)
            logger.info("Successfully registered character sheet tool with ToolCalling cog")
        else:
            logger.error("ToolCalling cog not found - character sheet tool will not be available!")

    async def cog_unload(self):
        """Cleanup when the cog unloads"""
        await self.character_manager.cleanup()
        logger.info("RPG cog unloaded")

    @app_commands.command(name="character", description="View your RPG character sheet")
    @app_commands.describe(
        channel_specific="Whether to view a channel-specific character (default: yes)"
    )
    async def view_character(
        self,
        interaction: discord.Interaction,
        channel_specific: Optional[bool] = True
    ):
        """View your character sheet"""
        await interaction.response.defer(thinking=True)

        try:
            channel_id = interaction.channel.id if channel_specific else None
            character = await self.character_manager.get_or_create_character(
                interaction.user.id,
                channel_id
            )

            # Create embed with character information
            embed = discord.Embed(
                title=f"{character.name}",
                description=f"Level {character.level} Adventurer",
                color=0x7289DA
            )

            # Core stats
            embed.add_field(
                name="Vitals",
                value=f"HP: {character.hp}/{character.max_hp}\nMP: {character.mp}/{character.max_mp}\nXP: {character.xp}\nGold: {character.gold}",
                inline=True
            )

            # Attributes
            embed.add_field(
                name="Attributes",
                value=f"STR: {character.strength}\nDEX: {character.dexterity}\nCON: {character.constitution}\nINT: {character.intelligence}\nWIS: {character.wisdom}\nCHA: {character.charisma}",
                inline=True
            )

            # Inventory
            inventory = character.get_inventory_list()
            if inventory:
                inv_text = ", ".join(inventory[:10])
                if len(inventory) > 10:
                    inv_text += f" (+{len(inventory) - 10} more)"
            else:
                inv_text = "Empty"
            embed.add_field(name="Inventory", value=inv_text, inline=False)

            # Custom stats if any
            custom = character.get_custom_stats()
            if custom:
                custom_text = "\n".join(f"{k}: {v}" for k, v in list(custom.items())[:5])
                embed.add_field(name="Custom Stats", value=custom_text, inline=False)

            # Footer with user info
            embed.set_footer(
                text=f"Character for {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error viewing character: {e}", exc_info=True)
            embed = discord.Embed(
                title="Error",
                description="Failed to load character sheet.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="rpg", description="Start an RPG adventure in a new thread")
    @app_commands.describe(
        prompt="Your adventure prompt or action",
        model="AI model to use (optional)",
        fun="Enable fun/unhinged mode for chaotic adventures"
    )
    async def rpg_command(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: Optional[str] = None,
        fun: Optional[bool] = False
    ):
        """Start an RPG adventure in a new thread"""
        # Check if we're in a guild channel that supports threads
        if not interaction.guild or isinstance(interaction.channel, discord.Thread):
            error_embed = create_error_embed("RPG threads can only be created in server text channels (not in DMs or existing threads).")
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            # Get AI commands cog
            ai_commands = self.bot.get_cog("AICommands")
            if not ai_commands:
                error_embed = create_error_embed("AI commands not available.")
                await interaction.followup.send(embed=error_embed)
                return

            # Get or create character for this user (will be associated with thread later)
            # For initial message, use None as channel_id since thread doesn't exist yet
            character = await self.character_manager.get_or_create_character(
                interaction.user.id,
                None  # Will be updated when thread is created
            )

            # Build character context
            char_context = self._build_character_context(character)

            # Build full system prompt with character context
            # If fun mode is enabled, prepend the fun prompt
            base_prompt = RPG_SYSTEM_PROMPT
            if fun:
                fun_prompt = config.get('fun_prompt', '')
                if fun_prompt:
                    base_prompt = f"{fun_prompt}\n\n{RPG_SYSTEM_PROMPT}"

            full_system_prompt = f"{base_prompt}\n\nCURRENT CHARACTER:\n{char_context}"

            # Format the prompt
            username = interaction.user.name
            formatted_prompt = f"{username}: {prompt}"

            # Use default model if none specified
            model_key = model or "gemini-3-flash-preview"

            # Process through AI with RPG tools only
            await ai_commands._process_ai_request(
                formatted_prompt,
                model_key,
                interaction=interaction,
                attachments=[],
                fun=fun,
                web_search=False,
                deep_research=False,
                tool_calling=True,
                max_tokens=8000,
                create_thread=True,
                allowed_tools=RPG_ALLOWED_TOOLS,
                custom_system_prompt=full_system_prompt
            )

            # Note: The thread creation happens in _process_ai_request with create_thread=True
            # However, we need to add "RPG Mode" to the footer. Since we can't easily modify
            # the embed after _process_ai_request, we'll need to rely on is_rpg_conversation_thread
            # detecting it some other way, OR we modify the first message after thread creation.

            # Let's modify the first message in the thread to add RPG Mode marker
            # Wait a moment for thread to be created
            await asyncio.sleep(0.5)

            # Find the thread that was just created (most recent thread by bot)
            # Note: channel.threads is a list property, not an async iterator
            for thread in interaction.channel.threads:
                # Check if this thread was just created (within last 5 seconds)
                if thread.owner_id == self.bot.user.id:
                    # Found the thread, modify the first message to add RPG Mode
                    async for msg in thread.history(limit=1, oldest_first=True):
                        if msg.author == self.bot.user and msg.embeds:
                            embed = msg.embeds[0]
                            current_footer = embed.footer.text if embed.footer else ""
                            if current_footer and "RPG Mode" not in current_footer:
                                lines = current_footer.split('\n')
                                if lines:
                                    lines[0] += " | RPG Mode"
                                    new_footer = '\n'.join(lines)
                                    embed.set_footer(text=new_footer)
                                    await msg.edit(embed=embed)
                                    logger.info(f"Added RPG Mode marker to thread: {thread.name}")
                    break

        except Exception as e:
            logger.error(f"Error starting RPG session: {e}", exc_info=True)
            error_embed = create_error_embed(f"Failed to start RPG session: {str(e)[:100]}")
            await interaction.followup.send(embed=error_embed)

    async def handle_rpg_thread_conversation(self, message: discord.Message):
        """Handle conversation in RPG threads"""
        try:
            # Get AI commands cog
            ai_commands = self.bot.get_cog("AICommands")
            if not ai_commands:
                logger.error("AICommands cog not found")
                return

            # Extract model and fun mode from the first bot message footer
            model_key = await self._detect_thread_model(message.channel)
            fun_mode = await self._detect_thread_fun_mode(message.channel)

            # Get character for this user and thread
            character = await self.character_manager.get_or_create_character(
                message.author.id,
                message.channel.id
            )

            # Build character context
            char_context = self._build_character_context(character)

            # Build full system prompt with character context
            # If fun mode is enabled, prepend the fun prompt
            base_prompt = RPG_SYSTEM_PROMPT
            if fun_mode:
                fun_prompt = config.get('fun_prompt', '')
                if fun_prompt:
                    base_prompt = f"{fun_prompt}\n\n{RPG_SYSTEM_PROMPT}"

            full_system_prompt = f"{base_prompt}\n\nCURRENT CHARACTER:\n{char_context}"

            # Gather conversation history from thread
            conversation_history = await self._build_conversation_history(message.channel, message)

            # Build context and prompt
            context_text, current_prompt = self._build_context_and_prompt(
                conversation_history, message
            )

            # Log processing info
            logger.info(
                f"Processing RPG thread message from {message.author.name} in thread {message.channel.name} (fun_mode={fun_mode})"
            )

            # Send thinking message
            thinking_msg = await message.reply("-# *The Game Master considers...*")

            try:
                # Combine context and current prompt
                full_prompt = self._combine_context_and_prompt(context_text, current_prompt)

                # Process the AI request with RPG tools only
                await ai_commands._process_ai_request(
                    prompt=full_prompt,
                    model_key=model_key,
                    reply_msg=message,
                    reply_user=message.author,
                    fun=fun_mode,
                    tool_calling=True,
                    allowed_tools=RPG_ALLOWED_TOOLS,
                    custom_system_prompt=full_system_prompt
                )
            finally:
                # Clean up thinking message
                try:
                    await thinking_msg.delete()
                except:
                    pass

        except Exception as e:
            logger.error(f"Error handling RPG thread conversation: {e}", exc_info=True)
            error_embed = create_error_embed(f"Error processing message: {str(e)[:100]}...")
            await message.channel.send(embed=error_embed)

    def _build_character_context(self, character) -> str:
        """Build a text representation of the character for the system prompt"""
        inventory = character.get_inventory_list()
        inv_text = ", ".join(inventory) if inventory else "Empty"

        custom_stats = character.get_custom_stats()
        custom_text = ", ".join(f"{k}: {v}" for k, v in custom_stats.items()) if custom_stats else "None"

        return f"""Name: {character.name}
Level: {character.level}
HP: {character.hp}/{character.max_hp}
MP: {character.mp}/{character.max_mp}
XP: {character.xp}
Gold: {character.gold}
Attributes: STR {character.strength}, DEX {character.dexterity}, CON {character.constitution}, INT {character.intelligence}, WIS {character.wisdom}, CHA {character.charisma}
Inventory: {inv_text}
Custom Stats: {custom_text}"""

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
            model_key = "gemini-3-flash-preview"

        return model_key

    async def _detect_thread_fun_mode(self, channel: discord.Thread) -> bool:
        """Detect if fun mode is used in a thread from bot message footers"""
        # Look through the first 20 messages to find bot messages with fun mode
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.author == self.bot.user and msg.embeds and msg.embeds[0].footer:
                footer_text = msg.embeds[0].footer.text
                if footer_text and "Fun Mode" in footer_text:
                    logger.info(f"Detected fun mode in RPG thread from footer: {footer_text}")
                    return True

        logger.info("No fun mode detected in RPG thread history")
        return False

    async def _build_conversation_history(self, channel: discord.Thread, current_message: discord.Message) -> list:
        """Build conversation history from thread messages"""
        conversation_history = []

        # Gather conversation history from thread (newest first, excluding current message)
        async for msg in channel.history(limit=50, before=current_message):
            if msg.author == self.bot.user:
                # Bot message - extract content from embed
                if msg.embeds and msg.embeds[0].description:
                    conversation_history.append(f"Game Master: {msg.embeds[0].description}")
            elif not msg.author.bot:
                # User message
                conversation_history.append(f"{msg.author.name}: {msg.content}")

        # Reverse to get chronological order (oldest first)
        conversation_history.reverse()
        return conversation_history

    def _build_context_and_prompt(self, conversation_history: list, message: discord.Message) -> tuple:
        """Build context text and current prompt, handling length limits"""
        max_context_length = 4000

        context_text = "\n".join(conversation_history)

        # Trim if too long
        while len(context_text) > max_context_length and conversation_history:
            conversation_history.pop(0)
            context_text = "\n".join(conversation_history)

        current_prompt = f"{message.author.name}: {message.content}"

        return context_text, current_prompt

    def _combine_context_and_prompt(self, context_text: str, current_prompt: str) -> str:
        """Combine context and current prompt into final prompt"""
        if context_text:
            return f"Previous conversation:\n{context_text}\n\nCurrent message:\n{current_prompt}"
        else:
            return current_prompt

    @app_commands.command(name="reset-character", description="Reset your character sheet to default values")
    @app_commands.describe(
        channel_specific="Whether to reset the channel-specific character (default: yes)"
    )
    async def reset_character(
        self,
        interaction: discord.Interaction,
        channel_specific: Optional[bool] = True
    ):
        """Reset character sheet to defaults"""
        await interaction.response.defer(thinking=True)

        try:
            channel_id = interaction.channel.id if channel_specific else None

            # Delete existing character if present
            existing = await self.character_manager.get_character(
                interaction.user.id,
                channel_id
            )
            if existing and existing.id:
                await self.character_manager.delete_character(existing.id)

            # Create fresh character
            character = await self.character_manager.get_or_create_character(
                interaction.user.id,
                channel_id
            )

            embed = discord.Embed(
                title="Character Reset",
                description=f"Your character has been reset to default values.",
                color=0x00FF00
            )
            embed.add_field(
                name=character.name,
                value=f"Level {character.level} | HP: {character.hp}/{character.max_hp} | MP: {character.mp}/{character.max_mp}"
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error resetting character: {e}", exc_info=True)
            embed = discord.Embed(
                title="Error",
                description="Failed to reset character sheet.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RPG(bot))
