import time
import os
import logging
import asyncio
import discord
import openai
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from api_utils import send_request, openrouterclient

from message_utils import delete_msg
from embed_utils import send_embed
from status_utils import update_status

fun_system_prompt = os.getenv("FUN_PROMPT", "")

logger = logging.getLogger(__name__)

class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="fun")
    async def fun(self, ctx, *, prompt: str):
        """
        Generate a fun reply using fun mode.

        Usage: !fun <your message>
        Optionally attach an image file to have it processed along with your message.
        """
        start_time = time.time()
        status_msg = await update_status(None, "...generating fun mode reply...", channel=ctx.channel)
        image_url = None

        # Check if the user's message has any image attachments.
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                    image_url = attachment.url
                    break  # Use the first image found.

        try:
            # Use tenacity to retry the API call in case of transient errors.
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    response = await send_request(
                        model="deepseek/deepseek-chat",
                        reply_mode="",  # In fun mode, no additional reply_mode instructions are needed.
                        message_content=prompt,
                        reference_message=None,
                        image_url=image_url,
                        custom_system_prompt=fun_system_prompt,
                        api_client=openrouterclient
                    )
                    break
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in fun command: %s", e)
            await ctx.send(f"Error generating fun mode response: {e}")
            return

        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        embed = discord.Embed(title="", description=response, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 | Fun Mode | generated in {elapsed} seconds")
        await send_embed(ctx.channel, embed, reply_to=ctx.message)

async def setup(bot):
    await bot.add_cog(FunCog(bot))