import time
import logging
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from generic_fun import perform_fun_query
from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

class FunModeModal(discord.ui.Modal, title="Fun Mode Reply"):
    user_prompt = discord.ui.TextInput(
        label="Additional prompt (optional)",
        style=discord.TextStyle.long,
        required=False,
        placeholder="Add extra context or instructions..."
    )
    
    def __init__(self, *, reference_message: str, api_cog, channel: discord.TextChannel):
        super().__init__()
        self.reference_message = reference_message
        self.api_cog = api_cog
        self.channel = channel
        self.start_time = time.time()

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        prompt_text = self.user_prompt.value or ""
        try:
            result, elapsed = await perform_fun_query(
                prompt=prompt_text,
                api_cog=self.api_cog,
                channel=self.channel,
                reference_message=self.reference_message
            )
        except Exception as e:
            logger.exception("Error in fun context menu command: %s", e)
            error_embed = Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            await send_embed(self.channel, error_embed)
            return

        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

@app_commands.context_menu(name="Fun Mode Reply")
async def fun_mode_reply(interaction: Interaction, message: discord.Message):
    if message.author == interaction.client.user:
        if message.embeds and message.embeds[0].description:
            content = message.embeds[0].description.strip()
        else:
            content = ""
    else:
        content = message.content

    ref_msg_content = f"Message from {message.author.name}: {content}"
    api_cog = interaction.client.get_cog("APIUtils")
    if not api_cog:
        await interaction.response.send_message("API utility cog not loaded!", ephemeral=True)
        return

    modal = FunModeModal(reference_message=ref_msg_content, api_cog=api_cog, channel=interaction.channel)
    await interaction.response.send_modal(modal)

class ContextFun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

async def setup(bot: commands.Bot):
    await bot.add_cog(ContextFun(bot))
    bot.tree.add_command(fun_mode_reply)