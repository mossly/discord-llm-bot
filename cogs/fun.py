import os
import time
import logging
import asyncio
import discord
import openai  # if needed by other parts of the file
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from message_utils import delete_msg
from embed_utils import send_embed
from status_utils import update_status

# Note: We no longer import send_request or openrouterclient from api_utils.
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
        Optionally attach an image file.
        """
        start_time = time.time()
        status_msg = await update_status(None, "...generating fun mode reply...", channel=ctx.channel)
        image_url = None

        # Check for any image attachments.
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                    image_url = attachment.url
                    break  # Use the first appropriate image found.

        # Get the API utilities cog.
        api_cog = ctx.bot.get_cog("APIUtils")
        if not api_cog:
            await delete_msg(status_msg)
            return await ctx.send("API utility cog not loaded!")

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    response = await api_cog.send_request(
                        model="deepseek/deepseek-chat",
                        reply_mode="",
                        message_content=prompt,
                        reference_message=None,
                        image_url=image_url,
                        custom_system_prompt=fun_system_prompt,
                        use_fun=True,
                    )
                    break  # Exit the retry loop on success.
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in fun command: %s", e)
            return await ctx.send(f"Error generating fun mode response: {e}")

        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        embed = discord.Embed(title="", description=response, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 | Fun Mode | generated in {elapsed} seconds")
        await send_embed(ctx.channel, embed, reply_to=ctx.message)

async def setup(bot):
    await bot.add_cog(FunCog(bot))