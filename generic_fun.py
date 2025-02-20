import time
import logging
import openai
import discord
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from status_utils import update_status
from message_utils import delete_msg

logger = logging.getLogger(__name__)

async def perform_fun_query(
    prompt: str,
    api_cog,  # an instance of your APIUtils cog
    channel: discord.TextChannel,
    image_url: str = None,
    reference_message: str = None,
) -> (str, float):
    """
    Core logic for a fun mode request.
    • Sends a fun API request using deepseek.
    • Updates and then deletes a status message.
    • Returns a tuple (result, elapsed_time)
    """
    start_time = time.time()
    status_msg = await update_status(None, "...generating fun reply...", channel=channel)
    try:
        model = "deepseek/deepseek-chat"
        reply_mode = ""  # No extra instructions in fun mode.
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
                    custom_system_prompt=api_cog.FUN_SYSTEM_PROMPT,  # load from APIUtils cog
                    use_fun=True,
                )
                break
        elapsed = round(time.time() - start_time, 2)
        await delete_msg(status_msg)
        return result, elapsed
    except Exception as e:
        await delete_msg(status_msg)
        logger.exception("Error in perform_fun_query: %s", e)
        raise