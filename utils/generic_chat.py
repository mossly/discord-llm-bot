import time
import logging
import openai
import discord
import aiohttp
import json
import uuid
import re
from datetime import datetime
import pytz
from typing import Optional
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from utils.response_formatter import extract_footnotes, build_standardized_footer
from utils.attachment_handler import process_attachments
from utils.conversation_logger import conversation_logger
from utils.quota_validator import quota_validator
from utils.reminder_manager import reminder_manager_v2

logger = logging.getLogger(__name__)

# Note: Functions moved to separate modules for better organization:
# - extract_footnotes, build_standardized_footer -> response_formatter.py
# - process_attachments -> attachment_handler.py
# - conversation logging -> conversation_logger.py
# - quota validation -> quota_validator.py

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
    """Legacy function signature - maintained for backward compatibility"""
    from utils.chat_data_classes import ChatRequest, APIConfig, ToolConfig

    # Convert legacy parameters to new data classes
    api_config = APIConfig(
        api=api,
        model=model or "gemini-3-flash-preview",
        max_tokens=max_tokens
    )

    tool_config = ToolConfig(
        use_tools=False,  # This function doesn't use tools
        deep_research=False
    )

    request = ChatRequest(
        prompt=prompt,
        user_id=user_id,
        channel=channel,
        api_config=api_config,
        tool_config=tool_config,
        image_url=image_url,
        reference_message=reference_message,
        use_fun=use_fun,
        web_search=web_search,
        interaction=interaction,
        username=username,
        reply_footer=reply_footer
    )

    return await perform_chat_query_enhanced(request, api_cog, duck_cog)


async def perform_chat_query_enhanced(
    request: 'ChatRequest',
    api_cog,
    duck_cog=None
) -> tuple[str, float, str]:
    """Enhanced chat query using structured request object"""
    start_time = time.time()
    original_prompt = request.prompt

    ddg_summary = None
    if duck_cog and request.web_search:
        try:
            search_query = await duck_cog.extract_search_query(original_prompt)
            if search_query:
                ddg_summary = await duck_cog.perform_ddg_search(search_query)
                if ddg_summary:
                    summary_result = await duck_cog.summarize_search_results(ddg_summary)
                    summary = summary_result[0] if isinstance(summary_result, tuple) else summary_result
                    if summary:
                        request.prompt = original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + summary
        except Exception as e:
            logger.exception("Error during DuckDuckGo search: %s", e)

    if ddg_summary:
        summary_text = ddg_summary[0] if isinstance(ddg_summary, tuple) else ddg_summary
        request.prompt = original_prompt + "\n\nSummary of Relevant Web Search Results:\n" + summary_text

    # Prepend user's current local time for LLM context
    try:
        user_timezone = await reminder_manager_v2.get_user_timezone(int(request.user_id))
        local_tz = pytz.timezone(user_timezone)
        current_local_time = datetime.now(local_tz)
        time_prefix = f"[Current time: {current_local_time.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}]\n\n"
        request.prompt = time_prefix + request.prompt
    except Exception as e:
        logger.warning(f"Failed to add timezone context for user {request.user_id}: {e}")

    # Check user quota before making API call
    can_proceed, quota_error = quota_validator.check_user_quota(request.user_id)
    if not can_proceed:
        return quota_error, 0, "Quota check failed"

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
                        model=request.api_config.model,
                        message_content=request.prompt,
                        reference_message=request.reference_message,
                        image_url=request.image_url,
                        api=request.api_config.api,
                        use_emojis=True if request.use_fun else False,
                        emoji_channel=request.channel,
                        use_fun=request.use_fun,
                        max_tokens=request.api_config.max_tokens
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

                            logger.warning(f"OpenRouter quota error: requested {request.api_config.max_tokens}, can afford {affordable_tokens}, retrying with {new_max_tokens}")

                            # Retry with reduced tokens
                            result, stats = await api_cog.send_request(
                                model=request.api_config.model,
                                message_content=request.prompt,
                                reference_message=request.reference_message,
                                image_url=request.image_url,
                                api=request.api_config.api,
                                use_emojis=True if request.use_fun else False,
                                emoji_channel=request.channel,
                                use_fun=request.use_fun,
                                max_tokens=new_max_tokens
                            )
                            # Add note about reduced tokens to stats
                            if stats:
                                stats['reduced_tokens'] = True
                                stats['original_max_tokens'] = request.api_config.max_tokens
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
                quota_validator.track_usage(request.user_id, total_cost)
        else:
            logger.warning("No generation stats received from API")

        # Extract footnotes from response and clean content
        cleaned_content, footnotes = extract_footnotes(result)

        # Apply emoji format substitution if emojis are enabled
        if request.use_fun and request.channel and request.channel.guild:
            cleaned_content = api_cog.substitute_emoji_formats(cleaned_content, request.channel.guild)

        # Build standardized footer
        footer = build_standardized_footer(
            model_name=request.reply_footer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=total_cost,
            elapsed_time=elapsed,
            footnotes=footnotes,
            use_fun=request.use_fun
        )

        # Log conversation to history
        await conversation_logger.log_conversation(
            user_id=request.user_id,
            user_message=original_prompt,
            bot_response=cleaned_content,
            model=request.api_config.model or "unknown",
            channel=request.channel,
            interaction=request.interaction,
            username=request.username,
            cost=total_cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

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
    username: str = None,
    allowed_tools: Optional[list] = None,
    custom_system_prompt: Optional[str] = None
) -> tuple[str, float, str]:
    """Legacy function signature - maintained for backward compatibility"""
    from utils.chat_data_classes import ChatRequest, APIConfig, ToolConfig

    # Convert legacy parameters to new data classes
    api_config = APIConfig(
        api=api,
        model=model or "gemini-3-flash-preview",
        max_tokens=max_tokens
    )

    tool_config = ToolConfig(
        use_tools=use_tools,
        force_tools=force_tools,
        allowed_tools=allowed_tools,
        max_iterations=max_iterations,
        deep_research=deep_research
    )

    request = ChatRequest(
        prompt=prompt,
        user_id=user_id,
        channel=channel,
        api_config=api_config,
        tool_config=tool_config,
        image_url=image_url,
        reference_message=reference_message,
        use_fun=use_fun,
        web_search=False,  # Handled by tools now
        interaction=interaction,
        username=username,
        reply_footer=reply_footer,
        custom_system_prompt=custom_system_prompt
    )

    return await perform_chat_query_with_tools_enhanced(request, api_cog, tool_cog, duck_cog)


async def perform_chat_query_with_tools_enhanced(
    request: 'ChatRequest',
    api_cog,
    tool_cog,
    duck_cog=None
) -> tuple[str, float, str]:
    """Enhanced chat query with tool calling support"""
    start_time = time.time()

    # Check user quota before starting
    can_proceed, quota_error = quota_validator.check_user_quota(request.user_id)
    if not can_proceed:
        return quota_error, 0, "Quota check failed"

    # If tools are disabled, use the standard flow
    if not request.tool_config.use_tools:
        return await perform_chat_query_enhanced(request, api_cog, duck_cog)

    # Get tool registry
    if not tool_cog:
        logger.warning("Tool cog not available, falling back to standard query")
        return await perform_chat_query_enhanced(request, api_cog, duck_cog)

    tool_registry = tool_cog.get_registry()
    available_tools = tool_registry.get_all_schemas(enabled_only=True)

    # Filter tools if allowed_tools is specified
    if request.tool_config.allowed_tools is not None:
        logger.info(f"Tool filtering - Allowed tools: {request.tool_config.allowed_tools}")
        logger.info(f"Tool filtering - Available tool names: {[tool.get('function', {}).get('name') for tool in available_tools]}")
        available_tools = [tool for tool in available_tools if tool.get("function", {}).get("name") in request.tool_config.allowed_tools]
        logger.info(f"Tool filtering - Filtered to {len(available_tools)} tools: {[tool.get('function', {}).get('name') for tool in available_tools]}")

    # Generate session ID for tool usage tracking
    session_id = str(uuid.uuid4())
    tool_cog.start_session(session_id)

    # Set Discord context for context-aware tools
    if request.channel:
        tool_cog.set_discord_context(request.channel)

    if not available_tools:
        logger.warning("No tools available, falling back to standard query")
        tool_cog.end_session(session_id)  # Clean up session
        return await perform_chat_query_enhanced(request, api_cog, duck_cog)

    # Build initial conversation with Discord context
    # Use custom system prompt if provided, otherwise use default
    if request.custom_system_prompt:
        base_system_prompt = request.custom_system_prompt
    else:
        base_system_prompt = api_cog.FUN_SYSTEM_PROMPT if request.use_fun else api_cog.SYSTEM_PROMPT

    # Add Discord context to system prompt
    discord_context = ""
    if request.channel:
        discord_context += f"\nCurrent Discord Context:\n"
        if request.channel.guild:
            discord_context += f"Server ID: {request.channel.guild.id}\n"
            discord_context += f"Server Name: {request.channel.guild.name}\n"
        else:
            discord_context += f"Context: Direct Message\n"
        discord_context += f"Channel ID: {request.channel.id}\n"
        if hasattr(request.channel, 'name') and request.channel.name:
            discord_context += f"Channel Name: {request.channel.name}\n"
        discord_context += f"Channel Type: {request.channel.type}\n\n"

    system_prompt = base_system_prompt + discord_context
    conversation_messages = [
        {"role": "system", "content": system_prompt}
    ]

    if request.reference_message:
        conversation_messages.append({"role": "user", "content": request.reference_message})

    # Add the user's message
    if request.image_url:
        content_list = [{"type": "text", "text": request.prompt}]
        # Add image handling similar to send_request
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(request.image_url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        mime_type = 'image/jpeg'  # Default
                        if request.image_url.lower().endswith('.png'):
                            mime_type = 'image/png'
                        elif request.image_url.lower().endswith('.webp'):
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
            conversation_messages.append({"role": "user", "content": request.prompt})
    else:
        conversation_messages.append({"role": "user", "content": request.prompt})

    # Tool calling loop
    total_cost = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for iteration in range(request.tool_config.max_iterations):
        try:
            # Determine tool choice
            if iteration == 0 and request.tool_config.force_tools:
                tool_choice = "required"
            else:
                tool_choice = "auto"

            # Make API call with tools
            response = await api_cog.send_request_with_tools(
                model=request.api_config.model,
                messages=conversation_messages,
                tools=available_tools,
                tool_choice=tool_choice,
                api=request.api_config.api,
                max_tokens=request.api_config.max_tokens
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
                    quota_validator.track_usage(request.user_id, iteration_cost)

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
                    request.user_id,
                    request.channel,
                    session_id,
                    request.api_config.model,
                    requesting_user_id=request.user_id  # Pass the actual Discord user making the request
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
                    quota_validator.track_usage(request.user_id, tool_usage["cost"])

                # Extract footnotes from response and clean content
                final_content = assistant_content or "I couldn't generate a response."
                cleaned_content, footnotes = extract_footnotes(final_content)

                # Apply emoji format substitution if emojis are enabled
                if request.use_fun and request.channel and request.channel.guild:
                    cleaned_content = api_cog.substitute_emoji_formats(cleaned_content, request.channel.guild)

                footer = build_standardized_footer(
                    model_name=request.reply_footer,
                    input_tokens=final_input_tokens,
                    output_tokens=final_output_tokens,
                    cost=final_cost,
                    elapsed_time=elapsed,
                    footnotes=footnotes,
                    use_fun=request.use_fun
                )

                # Log conversation to history
                await conversation_logger.log_conversation(
                    user_id=request.user_id,
                    user_message=request.prompt,
                    bot_response=cleaned_content,
                    model=request.api_config.model or "unknown",
                    channel=request.channel,
                    interaction=request.interaction,
                    username=request.username,
                    cost=final_cost,
                    input_tokens=final_input_tokens,
                    output_tokens=final_output_tokens
                )

                # Clean up session
                tool_cog.end_session(session_id)

                return cleaned_content, elapsed, footer

        except Exception as e:
            logger.exception(f"Error in tool calling iteration {iteration}: {e}")
            # Try to continue or fall back
            if iteration == 0:
                # First iteration failed, fall back to standard query
                tool_cog.end_session(session_id)  # Clean up session
                return await perform_chat_query_enhanced(request, api_cog, duck_cog)

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
            model=request.api_config.model,
            messages=conversation_messages,
            tools=None,  # No tools for final response
            tool_choice="none",
            api=request.api_config.api,
            max_tokens=request.api_config.max_tokens
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
                quota_validator.track_usage(request.user_id, iteration_cost)

        elapsed = round(time.time() - start_time, 2)

        # Add tool usage to totals
        tool_usage = tool_cog.get_session_usage_totals(session_id)
        final_input_tokens = total_input_tokens + tool_usage["input_tokens"]
        final_output_tokens = total_output_tokens + tool_usage["output_tokens"]
        final_cost = total_cost + tool_usage["cost"]

        # Add tool costs to user quota
        if tool_usage["cost"] > 0:
            quota_validator.track_usage(request.user_id, tool_usage["cost"])

        # Extract footnotes from response and clean content
        raw_content = final_response.get("content", "I couldn't generate a response.")
        cleaned_content, footnotes = extract_footnotes(raw_content)

        # Apply emoji format substitution if emojis are enabled
        if request.use_fun and request.channel and request.channel.guild:
            cleaned_content = api_cog.substitute_emoji_formats(cleaned_content, request.channel.guild)

        footer = build_standardized_footer(
            model_name=request.reply_footer,
            input_tokens=final_input_tokens,
            output_tokens=final_output_tokens,
            cost=final_cost,
            elapsed_time=elapsed,
            footnotes=footnotes,
            use_fun=request.use_fun
        )

        # Log conversation to history
        await conversation_logger.log_conversation(
            user_id=request.user_id,
            user_message=request.prompt,
            bot_response=cleaned_content,
            model=request.api_config.model or "unknown",
            channel=request.channel,
            interaction=request.interaction,
            username=request.username,
            cost=final_cost,
            input_tokens=final_input_tokens,
            output_tokens=final_output_tokens
        )

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
            quota_validator.track_usage(request.user_id, tool_usage["cost"])

        footer = build_standardized_footer(
            model_name=request.reply_footer,
            input_tokens=final_input_tokens,
            output_tokens=final_output_tokens,
            cost=final_cost,
            elapsed_time=elapsed,
            use_fun=request.use_fun
        )

        # Clean up session
        if tool_cog:
            tool_cog.end_session(session_id)

        return "Error generating final response after tool iterations.", elapsed, footer
