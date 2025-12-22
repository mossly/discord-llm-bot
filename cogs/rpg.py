"""
RPG Cog - Provides RPG character sheet management functionality
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Optional

from utils.character_sheet_manager import CharacterSheetManager

logger = logging.getLogger(__name__)


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
