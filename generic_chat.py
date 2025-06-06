import time
import logging
import openai
import discord
import aiohttp
import re
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from user_quotas import quota_manager

logger = logging.getLogger(__name__)

def build_standardized_footer(model_name: str, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0, elapsed_time: float = 0) -> str:
    """Build standardized footer for AI responses"""
    # First line: Clean model name only
    first_line = model_name
    
    # Second line: Usage stats
    usage_parts = []
    
    # Input tokens (abbreviate with k after 1000)
    if input_tokens > 0:
        if input_tokens >= 1000:
            input_str = f"{input_tokens / 1000:.1f}k"
        else:
            input_str = str(input_tokens)
        usage_parts.append(f"{input_str} input tokens")
    
    # Output tokens (abbreviate with k after 1000)
    if output_tokens > 0:
        if output_tokens >= 1000:
            output_str = f"{output_tokens / 1000:.1f}k"
        else:
            output_str = str(output_tokens)
        usage_parts.append(f"{output_str} output tokens")
    
    # Cost (show $x.xx, but to first non-zero digit if under $0.01)
    if cost >= 0.01:
        cost_str = f"${cost:.2f}"
    elif cost > 0:
        # Find first non-zero digit
        decimal_places = 2
        while cost < (1 / (10 ** decimal_places)) and decimal_places < 10:
            decimal_places += 1
        cost_str = f"${cost:.{decimal_places}f}"
    else:
        cost_str = "$0.00"
    usage_parts.append(cost_str)
    
    # Time
    if elapsed_time > 0:
        usage_parts.append(f"{elapsed_time} seconds")
    
    second_line = " | ".join(usage_parts)
    
    return f"{first_line}\n{second_line}"

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

        # Extract stats for standardized footer
        input_tokens = 0
        output_tokens = 0
        total_cost = 0
        
        if stats:
            input_tokens = stats.get('tokens_prompt', 0)
            output_tokens = stats.get('tokens_completion', 0)
            total_cost = stats.get('total_cost', 0)
            
            logger.info(f"Generation stats received: prompt_tokens={input_tokens}, completion_tokens={output_tokens}, total_cost={total_cost}")
            
            if total_cost is not None and total_cost > 0:
                # Track usage in user quota system
                if quota_manager.add_usage(user_id, total_cost):
                    logger.info(f"Tracked ${total_cost:.4f} usage for user {user_id}")
                else:
                    logger.warning(f"Failed to track usage for user {user_id}")
        else:
            logger.warning("No generation stats received from API")
        
        # Build standardized footer
        footer = build_standardized_footer(
            model_name=reply_footer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=total_cost,
            elapsed_time=elapsed
        )
        
        return result, elapsed, footer
            
    except Exception as e:
        logger.exception("Error in perform_chat_query: %s", e)
        raise