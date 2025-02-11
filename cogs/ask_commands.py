import time
import logging
import discord
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai

logger = logging.getLogger(__name__)

class AskCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ask")
    async def ask(self, ctx: commands.Context, *, prompt: str):
        """
        Standard query command.
        Usage: !ask <your message>
        """
        start_time = time.time()
        status_msg = await ctx.send("Generating reply...")
        
        # Check for an attached image, if any.
        image_url = None
        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    image_url = att.url
                    break

        # Retrieve the API utilities cog.
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await status_msg.delete()
            return await ctx.send("API utility cog not loaded!")
        
        try:
            model = "gpt-4o"
            reply_mode = "concise_prompt"
            # Optionally, wrap this call in tenacity to handle transient errors.
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    result = await api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=prompt,
                        image_url=image_url,
                    )
                    break
        except Exception as e:
            await status_msg.delete()
            logger.exception("Error in ask command: %s", e)
            return await ctx.send(f"Error generating reply: {e}")
        
        await status_msg.delete()
        elapsed = round(time.time() - start_time, 2)
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{model} | generated in {elapsed} seconds")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AskCommands(bot))