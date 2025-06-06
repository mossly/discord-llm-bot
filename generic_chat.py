import time
import logging
import openai
import discord
import aiohttp
import re
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from user_quotas import quota_manager

logger = logging.getLogger(__name__)

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

async def perform_chat_query(
    prompt: str,
    api_cog,
    channel: discord.TextChannel,
    user_id: str,
    duck_cog=None,
    image_url: str = None,
    reference_message: str = None,
    model: str = None,
    reply_footer: str = None,
    api: str = "openai",
    use_fun: bool = False,
    web_search: bool = False,
    max_tokens: int = 8000
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

    # Check user quota before making API call
    remaining_quota = quota_manager.get_remaining_quota(user_id)
    if remaining_quota == 0:
        return "❌ **Quota Exceeded**: You've reached your monthly usage limit. Your quota resets at the beginning of each month.", 0, "Quota exceeded"
    elif remaining_quota != float('inf') and remaining_quota < 0.01:  # Less than 1 cent remaining
        return f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Please be mindful of usage.", 0, f"${remaining_quota:.4f} remaining"

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
            wait=wait_exponential(min=1, max=10),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                try:
                    result, stats = await api_cog.send_request(
                        model=model,
                        message_content=prompt,
                        reference_message=reference_message,
                        image_url=image_url,
                        api=api,
                        use_emojis=True if use_fun else False,
                        emoji_channel=channel,
                        use_fun=use_fun,
                        max_tokens=max_tokens
                    )
                    break
                except openai.APIStatusError as e:
                    # Handle OpenRouter 402 quota error
                    if e.status_code == 402:
                        error_message = str(e)
                        # Try to get the error message from the exception
                        if hasattr(e, 'body') and isinstance(e.body, dict):
                            error_message = e.body.get('error', {}).get('message', error_message)
                        
                        # Extract the affordable tokens from error message
                        affordable_match = re.search(r'can only afford (\d+)', error_message)
                        if affordable_match:
                            affordable_tokens = int(affordable_match.group(1))
                            # Use 90% of affordable tokens to leave some buffer
                            new_max_tokens = int(affordable_tokens * 0.9)
                            
                            logger.warning(f"OpenRouter quota error: requested {max_tokens}, can afford {affordable_tokens}, retrying with {new_max_tokens}")
                            
                            # Retry with reduced tokens
                            result, stats = await api_cog.send_request(
                                model=model,
                                message_content=prompt,
                                reference_message=reference_message,
                                image_url=image_url,
                                api=api,
                                use_emojis=True if use_fun else False,
                                emoji_channel=channel,
                                use_fun=use_fun,
                                max_tokens=new_max_tokens
                            )
                            # Add note about reduced tokens to stats
                            if stats:
                                stats['reduced_tokens'] = True
                                stats['original_max_tokens'] = max_tokens
                                stats['reduced_max_tokens'] = new_max_tokens
                            break
                        else:
                            # Can't parse affordable tokens, re-raise
                            raise
                    else:
                        # Different error, re-raise
                        raise
        elapsed = round(time.time() - start_time, 2)

        footer_first_line = [reply_footer]
        
        if use_fun:
            footer_first_line.append("Fun Mode")
        if web_search:
            footer_first_line.append("Web Search")
        if stats and stats.get('reduced_tokens'):
            footer_first_line.append(f"Tokens reduced: {stats.get('original_max_tokens')} → {stats.get('reduced_max_tokens')}")
            
        footer_second_line = []
        
        if stats:
            tokens_prompt = stats.get('tokens_prompt', 0)
            tokens_completion = stats.get('tokens_completion', 0)
            total_cost = stats.get('total_cost', 0)
            
            logger.info(f"Generation stats received: prompt_tokens={tokens_prompt}, completion_tokens={tokens_completion}, total_cost={total_cost}")
            
            prompt_tokens_str = f"{tokens_prompt / 1000:.1f}k" if tokens_prompt >= 1000 else str(tokens_prompt)
            tokens_completion_str = f"{tokens_completion / 1000:.1f}k" if tokens_completion >= 1000 else str(tokens_completion)
            
            footer_second_line.append(f"{prompt_tokens_str} input tokens")
            footer_second_line.append(f"{tokens_completion_str} output tokens")
            
            if total_cost is not None:
                # Track usage in user quota system
                if quota_manager.add_usage(user_id, total_cost):
                    logger.info(f"Tracked ${total_cost:.4f} usage for user {user_id}")
                else:
                    logger.warning(f"Failed to track usage for user {user_id}")
                if total_cost > 0:
                    footer_second_line.append(f"${total_cost:.4f}")
                else:
                    footer_second_line.append("$0.0000")
        else:
            logger.warning("No generation stats received from API")
        
        footer_second_line.append(f"{elapsed} seconds")
        
        first_line = " | ".join(footer_first_line)
        second_line = " | ".join(footer_second_line)
        
        return result, elapsed, f"{first_line}\n{second_line}"
            
    except Exception as e:
        logger.exception("Error in perform_chat_query: %s", e)
        raise