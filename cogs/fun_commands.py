import time
import logging
import discord
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai
# Import our status and message helpers – just as in the original version.
from status_utils import update_status
from message_utils import delete_msg

logger = logging.getLogger(__name__)

class FunCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="fun")
    async def fun(self, ctx: commands.Context, *, prompt: str):
        """
        Fun mode reply command.
        Usage: !fun <your message>
        """
        start_time = time.time()
        # Set an initial status message (similar to "...reading request...")
        status_msg = await update_status(None, "...reading request...", ctx.channel)
        
        image_url = None
        if ctx.message.attachments:
            # Look for an image attachment and update the status accordingly
            for att in ctx.message.attachments:
                if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    image_url = att.url
                    break
            if image_url:
                status_msg = await update_status(status_msg, "...analyzing image...", ctx.channel)
        
        # Retrieve the API utilities cog (must be loaded)
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await delete_msg(status_msg)
            return await ctx.send("API utility cog not loaded!")
        
        try:
            model = "deepseek/deepseek-chat"
            reply_mode = ""  # No extra reply instructions in fun mode.
            # Use tenacity to retry the API call if transient errors occur.
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    # Update status right before generating the reply.
                    status_msg = await update_status(status_msg, "...generating reply...", ctx.channel)
                    result = await api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=prompt,
                        image_url=image_url,
                        custom_system_prompt=api_cog.FUN_SYSTEM_PROMPT,
                        use_fun=True,
                    )
                    break
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in fun command: %s", e)
            return await ctx.send(f"Error generating fun reply: {e}")
        
        # Delete the status message once the reply is ready.
        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCommands(bot))