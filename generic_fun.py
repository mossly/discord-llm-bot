import time
import logging
import openai
import discord
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from status_utils import update_status
from message_utils import delete_msg

logger = logging.getLogger(__name__)

async def get_guild_emoji_list(guild: discord.Guild) -> str:
    if not guild or not guild.emojis:
        logger.info("No guild or no emojis found in guild")
        return ""
    
    emoji_list = []
    for emoji in guild.emojis:
        if emoji.animated:
            emoji_list.append(f"<a:{emoji.name}:{emoji.id}>")
        else:
            emoji_list.append(f"<:{emoji.name}:{emoji.id}>")
    
    emoji_string = ",".join(emoji_list)
    logger.info(f"Compiled emoji list with {len(emoji_list)} emojis")
    return emoji_string

# Changes to generic_fun.py - perform_fun_query function
# Modify to ensure it uses FUN_PROMPT consistently

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
    
    emoji_list = await get_guild_emoji_list(channel.guild) if channel.guild else ""
    
    try:
        model = "deepseek/deepseek-chat"
        reply_mode = ""
        
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
                    use_fun=True,
                    api="openrouter"
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