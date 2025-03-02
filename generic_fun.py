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
    api_cog,
    channel: discord.TextChannel,
    image_url: str = None,
    reference_message: str = None,
    show_status: bool = True,
) -> (str, float):
    start_time = time.time()
    
    status_msg = None
    if show_status:
        status_msg = await update_status(None, "...generating fun reply...", channel=channel)
        
    try:
        model = "deepseek/deepseek-chat"
        
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
            wait=wait_exponential(min=1, max=10),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                result = await api_cog.send_request(
                    model=model,
                    message_content=prompt,
                    reference_message=reference_message,
                    image_url=image_url,
                    use_fun=True,
                    api="openrouter",
                    use_emojis=True,
                    emoji_channel=channel
                )
                break
        elapsed = round(time.time() - start_time, 2)
        
        if status_msg:
            await delete_msg(status_msg)
            
        return result, elapsed
    except Exception as e:
        if status_msg:
            await delete_msg(status_msg)
        logger.exception("Error in perform_fun_query: %s", e)
        raise