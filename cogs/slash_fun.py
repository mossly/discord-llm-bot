import time
import logging
import discord
from discord import app_commands, Interaction, Attachment, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai

# Import our helpers.
from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

class FunSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fun",
        description="Fun mode reply command. Provide a prompt, optionally attach an image or a message reference for context."
    )
    @app_commands.describe(
        prompt="Your fun prompt message.",
        attachment="Optional attachment (image file).",
        reference="Optional message to use as context (if replying to a message)."
    )
    async def fun(
        self,
        interaction: Interaction,
        prompt: str,
        attachment: Attachment = None,
        reference: discord.Message = None  # New optional parameter for replies
    ) -> None:
        # Defer the response so Discord knows we’re working on it.
        await interaction.response.defer()
        start_time = time.time()
        status_msg = await update_status(None, "...reading request...", channel=interaction.channel)

        # Process any image attachment.
        image_url = None
        if attachment:
            filename = attachment.filename.lower()
            if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                image_url = attachment.url
                # Currently image processing is disabled (as in the exclamation command).
                if image_url is not None:
                    image_url = None

        # Process a reference message (if provided).
        # This mimics our other commands by using the referenced content as extra context.
        reference_message = None
        if reference is not None:
            try:
                if reference.author == interaction.client.user:
                    # If the referenced message is from the bot and includes an embed, use its embed description.
                    if reference.embeds and reference.embeds[0].description:
                        reference_message = reference.embeds[0].description.strip()
                    else:
                        reference_message = ""
                else:
                    reference_message = reference.content
            except Exception as e:
                logger.exception("Failed to process reference message: %s", e)

        # Retrieve the API utilities cog.
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await delete_msg(status_msg)
            await interaction.followup.send("API utility cog not loaded!")
            return

        try:
            model = "deepseek/deepseek-chat"
            reply_mode = ""  # In fun mode, we don’t include extra reply instructions.
            # Use tenacity to retry the API call in case of transient errors.
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    status_msg = await update_status(status_msg, "...generating reply...", channel=interaction.channel)
                    result = await api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=prompt,
                        reference_message=reference_message,  # Pass along the referenced text (if any)
                        image_url=image_url,
                        custom_system_prompt=api_cog.FUN_SYSTEM_PROMPT,
                        use_fun=True,
                    )
                    break
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in fun slash command: %s", e)
            error_embed = Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            await send_embed(interaction.channel, error_embed)
            return

        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(FunSlash(bot))