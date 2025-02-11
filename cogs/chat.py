import time
import logging
import discord
import aiohttp
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import openai


from status_utils import update_status
from message_utils import delete_msg
from embed_utils import send_embed

# Global prompt definitions (as used in the original code)
O3MINI_PROMPT = "Use markdown formatting."
VERBOSE_PROMPT = "You are detailed & articulate. Include evidence and reasoning in your answers."
CREATIVE_PROMPT = (
    "You are a creative chatbot. Do your best to suggest original ideas and avoid cliches. "
    "Don't use overly poetic language. Be proactive and inventive and drive the conversation forward. "
    "Never use the passive voice where you can use the active voice. Do not end your message with a summary."
)

# Suffix definitions: if the user ends their prompt with -v or -c, use an alternate model and reply behavior.
SUFFIXES = {
    "-v": ("gpt-4o", VERBOSE_PROMPT, "gpt-4o | Verbose"),
    "-c": ("gpt-4o", CREATIVE_PROMPT, "gpt-4o | Creative")
}

# Default settings for normal requests.
DEFAULT_MODEL = "o3-mini"
DEFAULT_REPLY_MODE = O3MINI_PROMPT
DEFAULT_REPLY_FOOTER = "o3-mini | default"

logger = logging.getLogger(__name__)

class NormalCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="chat")
    async def chat(self, ctx: commands.Context, *, prompt: str):
        """
        Normal chatbot request.
        Usage: !chat <your message>
        (You may optionally attach a text file containing your prompt or images.)
        """
        start_time = time.time()
        status_msg = await update_status(None, "...reading request...", channel=ctx.channel)

        # First, process any .txt attachments by downloading their contents.
        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.filename.lower().endswith(".txt"):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(att.url) as response:
                                if response.status == 200:
                                    prompt = await response.text()
                                else:
                                    status_msg = await update_status(
                                        status_msg, f"...failed to download attachment. Code: {response.status}...", channel=ctx.channel
                                    )
                    except Exception as e:
                        status_msg = await update_status(
                            status_msg, "...failed to process text attachment...", channel=ctx.channel
                        )

        # Look for image attachments.
        image_url = None
        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    image_url = att.url
                    status_msg = await update_status(status_msg, "...analyzing image...", channel=ctx.channel)
                    break
        
        # If this command was invoked in reply to another message, try to fetch that reference.
        reference_message = None
        if ctx.message.reference:
            try:
                if ctx.message.reference.cached_message:
                    ref_msg = ctx.message.reference.cached_message
                else:
                    ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.author.id == self.bot.user.id:
                    status_msg = await update_status(status_msg, "...fetching bot reference...", channel=ctx.channel)
                    # If the bot’s reply was embedded, use the embed description.
                    if ref_msg.embeds and ref_msg.embeds[0].description:
                        reference_message = ref_msg.embeds[0].description.strip()
                    else:
                        reference_message = ""
                else:
                    status_msg = await update_status(status_msg, "...fetching user reference...", channel=ctx.channel)
                    reference_message = ref_msg.content
            except Exception:
                status_msg = await update_status(status_msg, "...unable to fetch reference...", channel=ctx.channel)

        # Process suffix flags in the prompt (e.g., "-v" for verbose or "-c" for creative).
        prompt = prompt.strip()
        model = DEFAULT_MODEL
        reply_mode = DEFAULT_REPLY_MODE
        reply_footer = DEFAULT_REPLY_FOOTER
        if len(prompt) > 2 and prompt[-2:] in SUFFIXES:
            suffix = prompt[-2:]
            model, reply_mode, reply_footer = SUFFIXES[suffix]
            prompt = prompt[:-2].strip()

        # IMPORTANT FIX: If an image is attached, force using gpt-4o-mini.
        if image_url is not None:
            model = "gpt-4o-mini"
            reply_footer = "gpt-4o-mini | default"

        original_content = prompt

        # Optionally perform a web search integration via DuckDuckGo (if the DuckDuckGo cog is loaded)
        duck_cog = self.bot.get_cog("DuckDuckGo")
        if duck_cog is not None:
            status_msg = await update_status(status_msg, "...trying web search...", channel=ctx.channel)
            try:
                ddg_summary = await duck_cog.search_and_summarize(original_content)
            except Exception:
                ddg_summary = None
            if ddg_summary:
                status_msg = await update_status(status_msg, "...web search complete...", channel=ctx.channel)
                modified_message = original_content + "\n\nSummary of Relevant Web Search Results:\n" + ddg_summary
            else:
                status_msg = await update_status(status_msg, "...no web search necessary...", channel=ctx.channel)
                modified_message = original_content
        else:
            modified_message = original_content

        # Retrieve the API utilities cog to make the request.
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await delete_msg(status_msg)
            return await ctx.send("API utility cog not loaded!")

        # Use tenacity to retry the API call (in case of transient errors).
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    status_msg = await update_status(status_msg, "...generating reply...", channel=ctx.channel)
                    result = await api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=modified_message,
                        reference_message=reference_message,
                        image_url=image_url,
                        custom_system_prompt=None
                    )
                    break
        except Exception as e:
            await delete_msg(status_msg)
            logger.exception("Error in chat command: %s", e)
            error_embed = discord.Embed(title="ERROR", description="x_x", color=0x32a956)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            await send_embed(ctx.channel, error_embed)
            return

        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{reply_footer} | generated in {elapsed} seconds")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(NormalCommands(bot))