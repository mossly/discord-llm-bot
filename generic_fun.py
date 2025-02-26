import time
import logging
import openai
import discord
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from status_utils import update_status
from message_utils import delete_msg

logger = logging.getLogger(__name__)

async def get_guild_emoji_list(guild: discord.Guild) -> str:
    """
    Retrieve all custom emojis from a guild and format them into a comma-separated string
    in Discord's emoji syntax format: <:name:id>,<:name:id>,...
    
    Args:
        guild: The Discord guild (server) to pull emojis from
    
    Returns:
        A string containing all custom emoji references in Discord format
    """
    if not guild or not guild.emojis:
        logger.info("No guild or no emojis found in guild")
        return ""
    
    emoji_list = []
    for emoji in guild.emojis:
        # Format depends on whether it's animated or not
        if emoji.animated:
            emoji_list.append(f"<a:{emoji.name}:{emoji.id}>")
        else:
            emoji_list.append(f"<:{emoji.name}:{emoji.id}>")
    
    # Join all emojis with commas
    emoji_string = ",".join(emoji_list)
    logger.info(f"Compiled emoji list with {len(emoji_list)} emojis")
    return emoji_string

async def perform_fun_query(
    prompt: str,
    api_cog,
    channel: discord.TextChannel,
    image_url: str = None,
    reference_message: str = None,
    show_status: bool = True,
) -> (str, float):
    """
    Core logic for a fun mode request.
    • Sends a fun API request using deepseek.
    • Updates and then deletes a status message.
    • Returns a tuple (result, elapsed_time)
    """
    start_time = time.time()
    
    # Only show status if requested (for text commands)
    status_msg = None
    if show_status:
        status_msg = await update_status(None, "...generating fun reply...", channel=channel)
    
    # Get emoji list from the guild
    emoji_list = await get_guild_emoji_list(channel.guild) if channel.guild else ""
    
    try:
        model = "deepseek/deepseek-chat"
        reply_mode = ""  # No extra instructions in fun mode.
        
        # Create a combined system prompt with emojis if available
        system_prompt = api_cog.FUN_SYSTEM_PROMPT
        if emoji_list:
            system_prompt += f"\n\nHere is a list of server specific emojis you should use: {emoji_list}"
        
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
                    custom_system_prompt=system_prompt,  # Now using our combined prompt
                    use_fun=True,
                )
                break
        elapsed = round(time.time() - start_time, 2)
        
        # Clean up status message if it was created
        if status_msg:
            await delete_msg(status_msg)
            
        return result, elapsed
    except Exception as e:
        # Clean up status message if it was created
        if status_msg:
            await delete_msg(status_msg)
        logger.exception("Error in perform_fun_query: %s", e)
        raise
