import time
import logging
import openai
import discord
import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from status_utils import update_status
from message_utils import delete_msg

logger = logging.getLogger(__name__)

# Shared prompt definitions and suffix settings.
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


async def process_attachments(prompt: str, attachments: list, is_slash: bool = False) -> (str, str):
    """
    Process attachments to update the prompt and extract an image URL if one is attached.
    For text file attachments, the file's content replaces the existing prompt.
    For image files, the URL is set (the first found is used).
    """
    image_url = None
    final_prompt = prompt
    if attachments:
        for att in attachments:
            filename = att.filename.lower()
            if filename.endswith(".txt"):
                try:
                    if is_slash:
                        file_bytes = await att.read()
                        final_prompt = file_bytes.decode("utf-8")
                    else:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(att.url) as response:
                                if response.status == 200:
                                    final_prompt = await response.text()
                                else:
                                    logger.warning(f"Failed to download attachment: {att.url} with status {response.status}")
                except Exception as e:
                    logger.exception("Error processing text attachment: %s", e)
            elif filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) and not image_url:
                # For image attachments, we just store the attachment URL
                # The API will fetch the image using proxy=None to allow for Discord CDN URLs
                image_url = att.proxy_url or att.url  # Use proxy_url if available as it's better for Discord CDN
    return final_prompt, image_url



def extract_suffixes(prompt: str) -> (str, str, str, str):
    """
    If the prompt ends with a known suffix (e.g. "-v" or "-c"), remove it and return the cleaned prompt
    along with the associated model, reply mode, and footer.
    """
    model = DEFAULT_MODEL
    reply_mode = DEFAULT_REPLY_MODE
    reply_footer = DEFAULT_REPLY_FOOTER
    cleaned_prompt = prompt.strip()
    if len(cleaned_prompt) > 2 and cleaned_prompt[-2:] in SUFFIXES:
        suffix = cleaned_prompt[-2:]
        model, reply_mode, reply_footer = SUFFIXES[suffix]
        cleaned_prompt = cleaned_prompt[:-2].strip()
    return cleaned_prompt, model, reply_mode, reply_footer


async def get_reference_message(ctx) -> str:
    """
    For text commands, if the invocation is a reply, fetches the reference message.
    Returns the content or embed description from the referenced message.
    """
    reference_message = ""
    if hasattr(ctx, "message") and ctx.message.reference:
        try:
            if ctx.message.reference.cached_message:
                ref_msg = ctx.message.reference.cached_message
            else:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if ref_msg.author.id == ctx.bot.user.id:
                if ref_msg.embeds and ref_msg.embeds[0].description:
                    reference_message = ref_msg.embeds[0].description.strip()
            else:
                reference_message = ref_msg.content
        except Exception as e:
            logger.exception("Failed to fetch reference message: %s", e)
    return reference_message


async def prepare_chat_parameters(prompt: str, attachments: list = None, ctx=None, is_slash: bool = False) -> (str, str, str, str, str, str):
    """
    Given a prompt and optional attachments, processes them and extracts:
      • final_prompt (possibly replaced by a text file’s content)
      • image_url if present
      • model, reply_mode, reply_footer via suffix extraction
      • reference_message (if ctx is provided and is not a slash command)
    """
    final_prompt, image_url = await process_attachments(prompt, attachments or [], is_slash=is_slash)
    final_prompt, model, reply_mode, reply_footer = extract_suffixes(final_prompt)
    reference_message = ""
    if not is_slash and ctx is not None:
        reference_message = await get_reference_message(ctx)
    return final_prompt, image_url, model, reply_mode, reply_footer, reference_message


async def perform_chat_query(
    prompt: str,
    api_cog,
    channel: discord.TextChannel,
    duck_cog=None,
    image_url: str = None,
    reference_message: str = None,
    model: str = DEFAULT_MODEL,
    reply_mode: str = DEFAULT_REPLY_MODE,
    reply_footer: str = DEFAULT_REPLY_FOOTER,
    show_status: bool = True,  # New parameter
) -> (str, float, str):
    """
    Core logic for a chat request:
      • Optionally appends a DuckDuckGo search summary (if duck_cog is available),
      • Uses a tenacity retry block to call the API,
      • Returns the API reply, elapsed time, and reply_footer.
    """
    start_time = time.time()
    original_prompt = prompt
    if duck_cog is not None:
        try:
            ddg_summary = await duck_cog.search_and_summarize(original_prompt)
        except Exception as e:
            logger.exception("Error during DuckDuckGo search: %s", e)
            ddg_summary = None
        if ddg_summary:
            prompt = original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + ddg_summary

    # Only show status if requested (for text commands)
    status_msg = None
    if show_status:
        status_msg = await update_status(None, "...generating reply...", channel=channel)
        
    try:
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
                    reference_message=reference_message,
                    image_url=image_url,
                    custom_system_prompt=None,
                )
                break
        elapsed = round(time.time() - start_time, 2)
        
        # Clean up status message if it was created
        if status_msg:
            await delete_msg(status_msg)
            
        return result, elapsed, reply_footer
    except Exception as e:
        # Clean up status message if it was created
        if status_msg:
            await delete_msg(status_msg)
        logger.exception("Error in perform_chat_query: %s", e)
        raise