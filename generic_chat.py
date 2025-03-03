import time
import logging
import openai
import discord
import aiohttp
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "o3-mini"
DEFAULT_REPLY_FOOTER = "o3-mini | default"

async def process_attachments(prompt: str, attachments: list, is_slash: bool = False) -> (str, str):
    image_url = None
    final_prompt = prompt
    if attachments:
        for att in attachments:
            filename = att.filename.lower()
            if filename.endswith(".txt"):
                try:
                    if is_slash:
                        file_bytes = await att.read()
                        final_prompt =  file_bytes.decode("utf-8")
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
                image_url = att.proxy_url or att.url
    return final_prompt, image_url


async def get_reference_message(ctx) -> str:
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
                reference_message = f"Message from {ref_msg.author.name}: {ref_msg.content}"
        except Exception as e:
            logger.exception("Failed to fetch reference message: %s", e)
    return reference_message


async def prepare_chat_parameters(prompt: str, attachments: list = None, ctx=None, is_slash: bool = False) -> (str, str, str, str, str, str):
    final_prompt, image_url = await process_attachments(prompt, attachments or [], is_slash=is_slash)

    model, reply_footer = DEFAULT_MODEL, DEFAULT_REPLY_FOOTER
    
    reference_message = ""
    if not is_slash and ctx is not None:
        reference_message = await get_reference_message(ctx)
        
    return final_prompt, image_url, model, reply_footer, reference_message

async def perform_chat_query(
    prompt: str,
    api_cog,
    channel: discord.TextChannel,
    duck_cog=None,
    image_url: str = None,
    reference_message: str = None,
    model: str = DEFAULT_MODEL,
    reply_footer: str = DEFAULT_REPLY_FOOTER,
    api: str = "openai",
    use_fun: bool = False,
    web_search: bool = False
) -> (str, float, str):
    start_time = time.time()
    original_prompt = prompt
    
    ddg_summary = None
    if duck_cog and web_search:
        try:
            search_query = await duck_cog.extract_search_query(original_prompt)
            if search_query:
                ddg_summary = await duck_cog.perform_ddg_search(search_query)
                if ddg_summary:
                    summary_result = await duck_cog.summarize_search_results(ddg_summary)
                    summary = summary_result[0] if isinstance(summary_result, tuple) else summary_result
                    if summary:
                        prompt = original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + summary
        except Exception as e:
            logger.exception("Error during DuckDuckGo search: %s", e)
    
    if ddg_summary:
        summary_text = ddg_summary[0] if isinstance(ddg_summary, tuple) else ddg_summary
        prompt = original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + summary_text

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
            wait=wait_exponential(min=1, max=10),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                result, stats = await api_cog.send_request(
                    model=model,
                    message_content=prompt,
                    reference_message=reference_message,
                    image_url=image_url,
                    api=api,
                    use_emojis=True if use_fun else False,
                    emoji_channel=channel,
                    use_fun=use_fun
                )
                break
        elapsed = round(time.time() - start_time, 2)

        footer_first_line = [reply_footer]
        
        if use_fun:
            footer_first_line.append("Fun Mode")
        if web_search:
            footer_first_line.append("Web Search")
            
        footer_second_line = []
        
        if stats:
            tokens_prompt = stats.get('tokens_prompt', 0)
            tokens_completion = stats.get('tokens_completion', 0)
            total_cost = stats.get('total_cost', 0)
            
            prompt_tokens_str = f"{tokens_prompt / 1000:.1f}k" if tokens_prompt >= 1000 else str(tokens_prompt)
            tokens_completion_str = f"{tokens_completion / 1000:.1f}k" if tokens_completion >= 1000 else str(tokens_completion)
            
            footer_second_line.append(f"{prompt_tokens_str} input tokens")
            footer_second_line.append(f"{tokens_completion_str} output tokens")
            
            if total_cost:
                footer_second_line.append(f"${total_cost:.2f}")
        
        footer_second_line.append(f"{elapsed} seconds")
        
        first_line = " | ".join(footer_first_line)
        second_line = " | ".join(footer_second_line)
        
        return result, elapsed, f"{first_line}\n{second_line}"
            
    except Exception as e:
        logger.exception("Error in perform_chat_query: %s", e)
        raise