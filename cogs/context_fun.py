import time
import logging
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai
from typing import Optional

from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

# ─── Modal for extra prompt input ───────────────────────────────
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
        # Use the modal input as additional prompt text.
        prompt_text = self.user_prompt.value or ""
        status_msg = await update_status(None, "...generating fun mode reply...", channel=self.channel)
        try:
            model = "deepseek/deepseek-chat"
            reply_mode = ""  # No extra reply instructions in fun mode.
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    # Use the additional prompt and the referenced message as context.
                    result = await self.api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=prompt_text,
                        reference_message=self.reference_message,
                        image_url=None,
                        custom_system_prompt=self.api_cog.FUN_SYSTEM_PROMPT,
                        use_fun=True,
                    )
                    break
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in fun context menu command: %s", e)
            error_embed = Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            await send_embed(self.channel, error_embed)
            return

        await delete_msg(status_msg)
        elapsed = round(time.time() - self.start_time, 2)
        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

# ─── Context Menu Command at the Module Level ───────────────
@app_commands.context_menu(name="Fun Mode Reply")
async def fun_mode_reply(interaction: Interaction, message: discord.Message):
    """
    When a user right‑clicks a message and selects “Fun Mode Reply”,
    this command extracts text from the target message (if the message is from the bot,
    uses its embed’s description) and then presents a modal for additional user input.
    """
    # Determine context text from the target message.
    if message.author == interaction.client.user:
        if message.embeds and message.embeds[0].description:
            content = message.embeds[0].description.strip()
        else:
            content = ""
    else:
        content = message.content

    ref_msg_content = f"Message from {message.author.name}: {content}"

    # Retrieve the APIUtils cog.
    api_cog = interaction.client.get_cog("APIUtils")
    if not api_cog:
        await interaction.response.send_message("API utility cog not loaded!", ephemeral=True)
        return

    # Show a modal so the user can optionally add extra prompt text.
    modal = FunModeModal(reference_message=ref_msg_content, api_cog=api_cog, channel=interaction.channel)
    await interaction.response.send_modal(modal)

# ─── Dummy Cog to Group Related Code (Optional) ───────────────
# (This cog can house additional helper methods if needed.)
class ContextFun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

async def setup(bot: commands.Bot):
    # Add our dummy cog.
    await bot.add_cog(ContextFun(bot))
    # Register the context menu command with the bot's application command tree.
    bot.tree.add_command(fun_mode_reply)