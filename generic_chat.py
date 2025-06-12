import time
import logging
import openai
import discord
import aiohttp
import re
import json
import uuid
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from user_quotas import quota_manager
from conversation_history import ConversationHistoryManager

logger = logging.getLogger(__name__)

# Initialize conversation history manager
conversation_history = ConversationHistoryManager()

def extract_footnotes(content: str) -> tuple[str, str]:
    """Extract footnotes from content and return (cleaned_content, footnotes)"""
    import re
    
    # First check for the explicit separator used by deep research
    if '===FOOTNOTES===' in content:
        parts = content.split('===FOOTNOTES===', 1)
        if len(parts) == 2:
            cleaned_content = parts[0].strip()
            footnotes = parts[1].strip()
            return cleaned_content, footnotes
    
    # Fallback to older patterns for backward compatibility
    # Patterns: "References:", "Sources:", "Footnotes:", or lines starting with [1], 1., etc.
    footnote_patterns = [
        r'\n\n(References?:.*?)$',
        r'\n\n(Sources?:.*?)$', 
        r'\n\n(Footnotes?:.*?)$',
        r'\n\n(\[[0-9]+\].*?)$',
        r'\n\n([0-9]+\..*?)$'
    ]
    
    for pattern in footnote_patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            footnotes = match.group(1).strip()
            # Remove the footnotes from the main content
            cleaned_content = content[:match.start()] + content[match.end():]
            return cleaned_content.strip(), footnotes
    
    # No footnotes found
    return content, ""

def build_standardized_footer(model_name: str, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0, elapsed_time: float = 0, footnotes: str = "") -> str:
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
    
    # Add footnotes if provided (utilize extra footer space)
    if footnotes:
        # Ensure we stay within Discord's 2048 character footer limit
        available_space = 2048 - len(first_line) - len(second_line) - 10  # Buffer for newlines
        if available_space > 50:  # Only add if we have reasonable space
            truncated_footnotes = footnotes[:available_space]
            if len(footnotes) > available_space:
                truncated_footnotes = truncated_footnotes.rsplit(' ', 1)[0] + "..."
            return f"{first_line}\n{second_line}\n{truncated_footnotes}"
    
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
    max_tokens: int = 8000,
    interaction=None,
    username: str = None
) -> tuple[str, float, str]:
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
        
        # Extract footnotes from response and clean content
        cleaned_content, footnotes = extract_footnotes(result)
        
        # Build standardized footer
        footer = build_standardized_footer(
            model_name=reply_footer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=total_cost,
            elapsed_time=elapsed,
            footnotes=footnotes
        )
        
        # Log conversation to history
        try:
            # Get server and channel info if available
            server_id = str(channel.guild.id) if channel.guild else None
            server_name = channel.guild.name if channel.guild else None
            channel_id = str(channel.id)
            channel_name = getattr(channel, 'name', 'DM' if isinstance(channel, discord.DMChannel) else 'Unknown')
            thread_id = str(channel.id) if isinstance(channel, discord.Thread) else None
            
            # Use provided username or try to get from interaction
            user_name = username
            if not user_name and interaction and hasattr(interaction, 'user'):
                user_name = interaction.user.name
            if not user_name:
                user_name = f"User_{user_id}"
            
            conversation_history.add_conversation(
                user_id=user_id,
                user_name=user_name,
                user_message=original_prompt,
                bot_response=cleaned_content,
                model=model or "unknown",
                server_id=server_id,
                server_name=server_name,
                channel_id=channel_id,
                channel_name=channel_name,
                thread_id=thread_id,
                cost=total_cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")
        
        return cleaned_content, elapsed, footer
            
    except Exception as e:
        logger.exception("Error in perform_chat_query: %s", e)
        raise


async def perform_chat_query_with_tools(
    prompt: str,
    api_cog,
    tool_cog,
    channel: discord.TextChannel,
    user_id: str,
    duck_cog=None,
    image_url: str = None,
    reference_message: str = None,
    model: str = None,
    reply_footer: str = None,
    api: str = "openai",
    use_fun: bool = False,
    use_tools: bool = True,
    force_tools: bool = False,
    deep_research: bool = False,
    max_tokens: int = 8000,
    max_iterations: int = 10,
    interaction=None,
    username: str = None
) -> tuple[str, float, str]:
    """Enhanced chat query with tool calling support"""
    start_time = time.time()
    
    # Check user quota before starting
    remaining_quota = quota_manager.get_remaining_quota(user_id)
    if remaining_quota == 0:
        return "❌ **Quota Exceeded**: You've reached your monthly usage limit. Your quota resets at the beginning of each month.", 0, "Quota exceeded"
    elif remaining_quota != float('inf') and remaining_quota < 0.01:
        return f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Please be mindful of usage.", 0, f"${remaining_quota:.4f} remaining"
    
    # If tools are disabled, use the standard flow
    if not use_tools:
        return await perform_chat_query(
            prompt=prompt,
            api_cog=api_cog,
            channel=channel,
            user_id=user_id,
            duck_cog=duck_cog,
            image_url=image_url,
            reference_message=reference_message,
            model=model,
            reply_footer=reply_footer,
            api=api,
            use_fun=use_fun,
            web_search=False,  # Handled by tools now
            max_tokens=max_tokens,
            interaction=interaction,
            username=username
        )
    
    # Get tool registry
    if not tool_cog:
        logger.warning("Tool cog not available, falling back to standard query")
        return await perform_chat_query(
            prompt=prompt,
            api_cog=api_cog,
            channel=channel,
            user_id=user_id,
            duck_cog=duck_cog,
            image_url=image_url,
            reference_message=reference_message,
            model=model,
            reply_footer=reply_footer,
            api=api,
            use_fun=use_fun,
            web_search=False,
            max_tokens=max_tokens,
            interaction=interaction,
            username=username
        )
    
    tool_registry = tool_cog.get_registry()
    available_tools = tool_registry.get_all_schemas(enabled_only=True)
    
    # Generate session ID for tool usage tracking
    session_id = str(uuid.uuid4())
    tool_cog.start_session(session_id)
    
    # Set Discord context for context-aware tools
    if channel:
        tool_cog.set_discord_context(channel)
    
    if not available_tools:
        logger.warning("No tools available, falling back to standard query")
        tool_cog.end_session(session_id)  # Clean up session
        return await perform_chat_query(
            prompt=prompt,
            api_cog=api_cog,
            channel=channel,
            user_id=user_id,
            duck_cog=duck_cog,
            image_url=image_url,
            reference_message=reference_message,
            model=model,
            reply_footer=reply_footer,
            api=api,
            use_fun=use_fun,
            web_search=False,
            max_tokens=max_tokens,
            interaction=interaction,
            username=username
        )
    
    # Build initial conversation with Discord context
    base_system_prompt = api_cog.FUN_SYSTEM_PROMPT if use_fun else api_cog.SYSTEM_PROMPT
    
    # Add Discord context to system prompt
    discord_context = ""
    if channel:
        discord_context += f"\nCurrent Discord Context:\n"
        discord_context += f"Server ID: {channel.guild.id}\n"
        discord_context += f"Server Name: {channel.guild.name}\n"
        discord_context += f"Channel ID: {channel.id}\n"
        discord_context += f"Channel Name: {channel.name}\n"
        discord_context += f"Channel Type: {channel.type}\n\n"
    
    system_prompt = base_system_prompt + discord_context
    conversation_messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    if reference_message:
        conversation_messages.append({"role": "user", "content": reference_message})
    
    # Add the user's message
    if image_url:
        content_list = [{"type": "text", "text": prompt}]
        # Add image handling similar to send_request
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        mime_type = 'image/jpeg'  # Default
                        if image_url.lower().endswith('.png'):
                            mime_type = 'image/png'
                        elif image_url.lower().endswith('.webp'):
                            mime_type = 'image/webp'
                        
                        import base64
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        content_list.append({
                            "type": "image_url", 
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                        })
            conversation_messages.append({"role": "user", "content": content_list})
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            conversation_messages.append({"role": "user", "content": prompt})
    else:
        conversation_messages.append({"role": "user", "content": prompt})
    
    # Tool calling loop
    total_cost = 0
    total_input_tokens = 0
    total_output_tokens = 0
    
    for iteration in range(max_iterations):
        try:
            # Determine tool choice
            if iteration == 0 and force_tools:
                tool_choice = "required"
            else:
                tool_choice = "auto"
            
            # Make API call with tools
            response = await api_cog.send_request_with_tools(
                model=model,
                messages=conversation_messages,
                tools=available_tools,
                tool_choice=tool_choice,
                api=api,
                max_tokens=max_tokens
            )
            
            if "error" in response:
                logger.error(f"API error: {response['error']}")
                return f"Error: {response['error']}", 0, "API Error"
            
            # Track usage
            if response.get("stats"):
                stats = response["stats"]
                input_tokens = stats.get("tokens_prompt", 0)
                output_tokens = stats.get("tokens_completion", 0)
                
                # Calculate cost
                if "total_cost" in stats:
                    iteration_cost = stats["total_cost"]
                else:
                    # Estimate cost based on tokens
                    iteration_cost = (input_tokens * 0.00001 + output_tokens * 0.00003)  # Example pricing
                
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += iteration_cost
                
                # Track usage
                if iteration_cost > 0:
                    quota_manager.add_usage(user_id, iteration_cost)
            
            # Add assistant message to history
            assistant_content = response.get("content")
            tool_calls = response.get("tool_calls", [])
            
            if tool_calls:
                # Add assistant message with tool calls
                conversation_messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": tool_calls
                })
                
                
                # Execute tools with user context for security
                tool_results = await tool_cog.process_tool_calls(
                    tool_calls,
                    user_id,
                    channel,
                    session_id,
                    model,
                    requesting_user_id=user_id  # Pass the actual Discord user making the request
                )
                
                # Add tool results to conversation
                formatted_results = tool_cog.format_tool_results_for_llm(tool_results)
                conversation_messages.extend(formatted_results)
                
                # Continue to next iteration
                continue
            else:
                elapsed = round(time.time() - start_time, 2)
                
                # Add tool usage to totals
                tool_usage = tool_cog.get_session_usage_totals(session_id)
                final_input_tokens = total_input_tokens + tool_usage["input_tokens"]
                final_output_tokens = total_output_tokens + tool_usage["output_tokens"]
                final_cost = total_cost + tool_usage["cost"]
                
                # Add tool costs to user quota
                if tool_usage["cost"] > 0:
                    quota_manager.add_usage(user_id, tool_usage["cost"])
                
                # Extract footnotes from response and clean content
                final_content = assistant_content or "I couldn't generate a response."
                cleaned_content, footnotes = extract_footnotes(final_content)
                
                footer = build_standardized_footer(
                    model_name=reply_footer,
                    input_tokens=final_input_tokens,
                    output_tokens=final_output_tokens,
                    cost=final_cost,
                    elapsed_time=elapsed,
                    footnotes=footnotes
                )
                
                # Log conversation to history
                try:
                    # Get server and channel info if available
                    server_id = str(channel.guild.id) if channel.guild else None
                    server_name = channel.guild.name if channel.guild else None
                    channel_id = str(channel.id)
                    channel_name = getattr(channel, 'name', 'DM' if isinstance(channel, discord.DMChannel) else 'Unknown')
                    thread_id = str(channel.id) if isinstance(channel, discord.Thread) else None
                    
                    # Use provided username or try to get from interaction
                    user_name = username
                    if not user_name and interaction and hasattr(interaction, 'user'):
                        user_name = interaction.user.name
                    if not user_name:
                        user_name = f"User_{user_id}"
                    
                    conversation_history.add_conversation(
                        user_id=user_id,
                        user_name=user_name,
                        user_message=prompt,
                        bot_response=cleaned_content,
                        model=model or "unknown",
                        server_id=server_id,
                        server_name=server_name,
                        channel_id=channel_id,
                        channel_name=channel_name,
                        thread_id=thread_id,
                        cost=final_cost,
                        input_tokens=final_input_tokens,
                        output_tokens=final_output_tokens
                    )
                except Exception as e:
                    logger.error(f"Failed to log conversation: {e}")
                
                # Clean up session
                tool_cog.end_session(session_id)
                
                return cleaned_content, elapsed, footer
                
        except Exception as e:
            logger.exception(f"Error in tool calling iteration {iteration}: {e}")
            # Try to continue or fall back
            if iteration == 0:
                # First iteration failed, fall back to standard query
                tool_cog.end_session(session_id)  # Clean up session
                return await perform_chat_query(
                    prompt=prompt,
                    api_cog=api_cog,
                    channel=channel,
                    user_id=user_id,
                    duck_cog=duck_cog,
                    image_url=image_url,
                    reference_message=reference_message,
                    model=model,
                    reply_footer=reply_footer,
                    api=api,
                    use_fun=use_fun,
                    web_search=False,
                    max_tokens=max_tokens
                )
    
    # Max iterations reached - send message to model to generate final output
    elapsed = round(time.time() - start_time, 2)
    
    # Add system message instructing the model to provide final output
    conversation_messages.append({
        "role": "system",
        "content": "Maximum tool iterations reached. Please provide your final response based on the information gathered so far. Do not attempt to use any more tools."
    })
    
    # Make final API call without tools
    try:
        final_response = await api_cog.send_request_with_tools(
            model=model,
            messages=conversation_messages,
            tools=None,  # No tools for final response
            tool_choice="none",
            api=api,
            max_tokens=max_tokens
        )
        
        if "error" in final_response:
            logger.error(f"Final API error: {final_response['error']}")
            return f"Error: {final_response['error']}", elapsed, "API Error"
        
        # Track final usage
        if final_response.get("stats"):
            stats = final_response["stats"]
            input_tokens = stats.get("tokens_prompt", 0)
            output_tokens = stats.get("tokens_completion", 0)
            
            if "total_cost" in stats:
                iteration_cost = stats["total_cost"]
            else:
                iteration_cost = (input_tokens * 0.00001 + output_tokens * 0.00003)
            
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            total_cost += iteration_cost
            
            if iteration_cost > 0:
                quota_manager.add_usage(user_id, iteration_cost)
        
        elapsed = round(time.time() - start_time, 2)
        
        # Add tool usage to totals
        tool_usage = tool_cog.get_session_usage_totals(session_id)
        final_input_tokens = total_input_tokens + tool_usage["input_tokens"]
        final_output_tokens = total_output_tokens + tool_usage["output_tokens"]
        final_cost = total_cost + tool_usage["cost"]
        
        # Add tool costs to user quota
        if tool_usage["cost"] > 0:
            quota_manager.add_usage(user_id, tool_usage["cost"])
        
        # Extract footnotes from response and clean content
        raw_content = final_response.get("content", "I couldn't generate a response.")
        cleaned_content, footnotes = extract_footnotes(raw_content)
        
        footer = build_standardized_footer(
            model_name=reply_footer,
            input_tokens=final_input_tokens,
            output_tokens=final_output_tokens,
            cost=final_cost,
            elapsed_time=elapsed,
            footnotes=footnotes
        )
        
        # Log conversation to history
        try:
            # Get server and channel info if available
            server_id = str(channel.guild.id) if channel.guild else None
            server_name = channel.guild.name if channel.guild else None
            channel_id = str(channel.id)
            channel_name = getattr(channel, 'name', 'DM' if isinstance(channel, discord.DMChannel) else 'Unknown')
            thread_id = str(channel.id) if isinstance(channel, discord.Thread) else None
            
            # Use provided username or try to get from interaction
            user_name = username
            if not user_name and interaction and hasattr(interaction, 'user'):
                user_name = interaction.user.name
            if not user_name:
                user_name = f"User_{user_id}"
            
            conversation_history.add_conversation(
                user_id=user_id,
                user_name=user_name,
                user_message=prompt,
                bot_response=cleaned_content,
                model=model or "unknown",
                server_id=server_id,
                server_name=server_name,
                channel_id=channel_id,
                channel_name=channel_name,
                thread_id=thread_id,
                cost=final_cost,
                input_tokens=final_input_tokens,
                output_tokens=final_output_tokens
            )
        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")
        
        # Clean up session
        tool_cog.end_session(session_id)
        
        return cleaned_content, elapsed, footer
        
    except Exception as e:
        logger.exception(f"Error in final response generation: {e}")
        
        # Add tool usage to totals even in error case
        tool_usage = tool_cog.get_session_usage_totals(session_id) if tool_cog else {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        final_input_tokens = total_input_tokens + tool_usage["input_tokens"]
        final_output_tokens = total_output_tokens + tool_usage["output_tokens"]
        final_cost = total_cost + tool_usage["cost"]
        
        # Add tool costs to user quota
        if tool_usage["cost"] > 0:
            quota_manager.add_usage(user_id, tool_usage["cost"])
        
        footer = build_standardized_footer(
            model_name=reply_footer,
            input_tokens=final_input_tokens,
            output_tokens=final_output_tokens,
            cost=final_cost,
            elapsed_time=elapsed
        )
        
        # Clean up session
        if tool_cog:
            tool_cog.end_session(session_id)
        
        return "Error generating final response after tool iterations.", elapsed, footer