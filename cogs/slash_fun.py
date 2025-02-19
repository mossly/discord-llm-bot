import time
import logging
import discord
from discord import app_commands, Interaction, Attachment, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai
from typing import Optional

# Import our status and message helpers – as used in other fun commands.
from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

class FunSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fun",
        description="Fun mode reply command. Provide a prompt and optionally attach an image or a reference (message URL or ID) for context."
    )
    @app_commands.describe(
        prompt="Your fun prompt message.",
        attachment="Optional image attachment.",
        reference="Optional message URL or ID from this channel to use as context."
    )
    async def fun(
        self,
        interaction: Interaction,
        prompt: str,
        attachment: Optional[Attachment] = None,
        reference: Optional[str] = None  # Changed from discord.Message to str
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
                # If image processing is not enabled (as per your example), we force image_url to None.
                if image_url is not None:
                    image_url = None

        # Process a reference message if provided.
        reference_message = None
        if reference:
            try:
                # Try to extract a message ID.
                # The user can provide either a full URL (e.g. https://discord.com/channels/...) or just the message ID.
                parts = reference.split('/')
                possible_id = parts[-1] if parts[-1].isdigit() else reference
                msg_id = int(possible_id)
                ref_msg = await interaction.channel.fetch_message(msg_id)
                if ref_msg.author == interaction.client.user:
                    # If the referenced message is from our bot and includes an embed, use its embed description.
                    if ref_msg.embeds and ref_msg.embeds[0].description:
                        reference_message = ref_msg.embeds[0].description.strip()
                    else:
                        reference_message = ""
                else:
                    reference_message = ref_msg.content
            except Exception as e:
                logger.exception("Failed to process reference parameter: %s", e)

        # Retrieve the API utilities cog.
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await delete_msg(status_msg)
            await interaction.followup.send("API utility cog not loaded!")
            return

        try:
            model = "deepseek/deepseek-chat"
            reply_mode = ""  # In fun mode, we don’t add extra reply instructions.
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
                        reference_message=reference_message,  # Passing the extracted reference.
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