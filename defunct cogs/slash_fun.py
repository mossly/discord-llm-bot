import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands

from generic_fun import perform_fun_query

logger = logging.getLogger(__name__)

class FunSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fun",
        description="Fun mode reply command. Provide a prompt and optionally attach an image."
    )
    async def fun(self, interaction: Interaction, prompt: str, attachment: Attachment = None) -> None:
        await interaction.response.defer()
        image_url = None
        if attachment:
            filename = attachment.filename.lower()
            if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                image_url = attachment.url

        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            return await interaction.followup.send("API utility cog not loaded!")
        
        try:
            result, elapsed = await perform_fun_query(prompt, api_cog, interaction.channel, image_url=image_url)
        except Exception as e:
            logger.exception("Error in fun slash command: %s", e)
            return await interaction.followup.send(f"Error generating reply: {e}")

        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(FunSlash(bot))