import time
import logging
import asyncio
import openai
from discord import app_commands, Interaction, Attachment, Embed
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

# Constants (unchanged from your original chat cog)
O3MINI_PROMPT = "Use markdown formatting."
VERBOSE_PROMPT = "You are detailed & articulate. Include evidence and reasoning in your answers."
CREATIVE_PROMPT = (
    "You are a creative chatbot. Do your best to suggest original ideas and avoid cliches. "
    "Don't use overly poetic language. Be proactive and inventive and drive the conversation forward. "
    "Never use the passive voice where you can use the active voice. Do not end your message with a summary."
)

SUFFIXES = {
    "-v": ("gpt-4o", VERBOSE_PROMPT, "gpt-4o | Verbose"),
    "-c": ("gpt-4o", CREATIVE_PROMPT, "gpt-4o | Creative")
}

DEFAULT_MODEL = "o3-mini"
DEFAULT_REPLY_MODE = O3MINI_PROMPT
DEFAULT_REPLY_FOOTER = "o3-mini | default"

logger = logging.getLogger(__name__)

class ChatSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Shortened the description to be 100 characters or less.
    @app_commands.command(
        name="chat",
        description="Generate a reply using your prompt; optionally attach a text file or image.",
        dm_permission=True
    )
    async def chat(
        self,
        interaction: Interaction,
        prompt: str,
        attachment: Attachment = None
    ) -> None:
        # Defer the response so Discord knows we are working
        await interaction.response.defer()

        start_time = time.time()
        image_url = None

        # Process an attachment if provided
        if attachment:
            filename = attachment.filename.lower()
            if filename.endswith(".txt"):
                try:
                    file_bytes = await attachment.read()
                    prompt = file_bytes.decode("utf-8")
                except Exception as e:
                    await interaction.followup.send(f"Error processing text file: {e}")
                    return
            elif filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                image_url = attachment.url

        original_prompt = prompt

        # Process suffix flags if present
        prompt = prompt.strip()
        model = DEFAULT_MODEL
        reply_mode = DEFAULT_REPLY_MODE
        reply_footer = DEFAULT_REPLY_FOOTER
        if len(prompt) > 2 and prompt[-2:] in SUFFIXES:
            suffix = prompt[-2:]
            model, reply_mode, reply_footer = SUFFIXES[suffix]
            prompt = prompt[:-2].strip()

        # If an image is attached, force a model change
        if image_url is not None:
            model = "gpt-4o-mini"
            reply_footer = "gpt-4o-mini | default"

        # Optionally, integrate DuckDuckGo search if its cog is loaded
        modified_message = original_prompt
        duck_cog = self.bot.get_cog("DuckDuckGo")
        if duck_cog is not None:
            try:
                ddg_summary = await duck_cog.search_and_summarize(original_prompt)
            except Exception:
                ddg_summary = None
            if ddg_summary:
                modified_message = (
                    original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + ddg_summary
                )

        # Get the API utilities cog for making requests
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            await interaction.followup.send("API utility cog not loaded!")
            return

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (openai.APIError, openai.APIConnectionError, openai.RateLimitError)
                ),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                with attempt:
                    result = await api_cog.send_request(
                        model=model,
                        reply_mode=reply_mode,
                        message_content=modified_message,
                        reference_message=None,  # No reference in slash commands
                        image_url=image_url,
                        custom_system_prompt=None,
                    )
                    break
        except Exception as e:
            logger.exception("Error in chat slash command: %s", e)
            await interaction.followup.send(f"Error generating reply: {e}")
            return

        elapsed = round(time.time() - start_time, 2)
        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{reply_footer} | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChatSlash(bot))