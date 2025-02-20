import time
import logging
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai

from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

# This modal gathers an optional additional prompt from the user.
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
        # Use the modal value as the main prompt (may be empty).
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
                    # Pass the additional prompt as message_content,
                    # and the reference message (from the right-clicked message)
                    # as reference_message.
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
        await interaction.response.send_message(embed=embed)

# This cog registers a context menu command that appears when you right‑click on any message.
class FunModeContext(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.context_menu(name="Fun Mode Reply")
    async def fun_mode_reply(self, interaction: Interaction, message: discord.Message):
        # Determine what text to send as context.
        # If the target message is from our bot and has an embed,
        # use the embed’s description; otherwise, use the plain content.
        if message.author == self.bot.user:
            if message.embeds and message.embeds[0].description:
                ref_msg_content = message.embeds[0].description.strip()
            else:
                ref_msg_content = ""
        else:
            ref_msg_content = message.content

        # Retrieve the API utilities cog.
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await interaction.response.send_message("API utility cog not loaded!", ephemeral=True)
            return

        # Show a modal to let the user supply additional prompt text.
        modal = FunModeModal(reference_message=ref_msg_content, api_cog=api_cog, channel=interaction.channel)
        await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(FunModeContext(bot))