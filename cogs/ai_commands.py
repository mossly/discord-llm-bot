import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from typing import Optional, Literal
from utils.embed_utils import send_embed, create_error_embed
import os

logger = logging.getLogger(__name__)

# Default model to use as fallback
DEFAULT_MODEL = "gemini-2.5-flash-preview"

# Model type definition
ModelChoices = Literal[
    "gpt-4o-mini",
    "o4-mini", 
    "claude-sonnet-4",
    "deepseek-r1-0528",
    "gemini-2.5-pro-preview",
    "gemini-2.5-flash-preview",
    "grok-3-beta"
]

# Hardcoded models configuration
# Note: api_model format depends on the API:
#   - For OpenRouter API: use "provider/model" format (e.g., "anthropic/claude-3", "google/gemini-2.0")
#   - For OpenAI API: use just the model name (e.g., "gpt-4o-mini", "o1-preview")
MODELS_CONFIG = {
    "gpt-4o-mini": {
        "name": "GPT-4o-mini",
        "default_footer": "GPT-4o-mini",
        "api_model": "gpt-4o-mini",
        "supports_images": True,
        "supports_tools": True,
        "api": "openai",
        "enabled": True,
        "admin_only": False
    },
    "o4-mini": {
        "name": "o4-mini",
        "default_footer": "o4-mini", 
        "api_model": "o4-mini",
        "supports_images": True,
        "supports_tools": True,
        "api": "openai",
        "enabled": True,
        "admin_only": False
    },
    "claude-sonnet-4": {
        "name": "Claude Sonnet 4",
        "default_footer": "Claude Sonnet 4",
        "api_model": "anthropic/claude-sonnet-4",
        "supports_images": True,
        "supports_tools": True,
        "api": "openrouter",
        "enabled": True,
        "admin_only": False
    },
    "deepseek-r1-0528": {
        "name": "DeepSeek R1",
        "default_footer": "DeepSeek R1",
        "api_model": "deepseek/deepseek-r1-0528",
        "supports_images": False,
        "supports_tools": True,
        "api": "openrouter",
        "enabled": True,
        "admin_only": False
    },
    "gemini-2.5-pro-preview": {
        "name": "Gemini 2.5 Pro",
        "default_footer": "Gemini 2.5 Pro",
        "api_model": "google/gemini-2.5-pro-preview",
        "supports_images": True,
        "supports_tools": True,
        "api": "openrouter",
        "enabled": True,
        "admin_only": False
    },
    "gemini-2.5-flash-preview": {
        "name": "Gemini 2.5 Flash",
        "default_footer": "Gemini 2.5 Flash",
        "api_model": "google/gemini-2.5-flash-preview-05-20:thinking",
        "supports_images": True,
        "supports_tools": True,
        "api": "openrouter",
        "enabled": True,
        "admin_only": False
    },
    "grok-3-beta": {
        "name": "Grok 3",
        "default_footer": "Grok 3",
        "api_model": "x-ai/grok-3-beta",
        "supports_images": True,
        "supports_tools": True,
        "api": "openrouter",
        "enabled": True,
        "admin_only": False
    }
}


class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"Loaded {len(MODELS_CONFIG)} hardcoded models")
    
    def _get_model_config(self, model_key: str) -> dict:
        """Get configuration for a specific model"""
        return MODELS_CONFIG.get(model_key, {})
    
    def _get_available_models(self, user_id: int) -> dict:
        """Get available models for a user"""
        available = {}
        is_admin = self._is_admin(user_id)
        
        for key, config in MODELS_CONFIG.items():
            if config.get('enabled', False):
                if not config.get('admin_only', False) or is_admin:
                    available[key] = config
        
        return available
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        # Check environment variable for admin IDs
        admin_ids_str = os.getenv("BOT_ADMIN_IDS", "")
        if admin_ids_str:
            try:
                admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
                if user_id in admin_ids:
                    return True
            except ValueError:
                pass
        
        # Check admin_ids.txt file
        try:
            with open("admin_ids.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        try:
                            if int(line) == user_id:
                                return True
                        except ValueError:
                            continue
        except FileNotFoundError:
            pass
        
        return False
    
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None, attachments=None, reference_message=None, image_url=None, reply_msg: Optional[discord.Message] = None, fun: bool = False, web_search: bool = False, deep_research: bool = False, tool_calling: bool = True, reply_user=None, max_tokens: int = 8000, create_thread: bool = False):
        # Debug logging for thread conversations
        if reply_msg and not ctx and not interaction:
            logger.info(f"_process_ai_request called for thread conversation - reply_msg.channel: {reply_msg.channel}, type: {type(reply_msg.channel) if reply_msg.channel else 'None'}")
        
        # Get user ID and username for quota tracking and model availability check
        if ctx:
            user_id = str(ctx.author.id)
            user_id_int = ctx.author.id
            username = ctx.author.name
        elif interaction:
            user_id = str(interaction.user.id)
            user_id_int = interaction.user.id
            username = interaction.user.name
        elif reply_user:
            user_id = str(reply_user.id)
            user_id_int = reply_user.id
            username = reply_user.name
        else:
            user_id = "unknown"
            user_id_int = 0
            username = "Unknown"
        
        # Check if model is available to this user
        available_models = self._get_available_models(user_id_int)
        if model_key not in available_models:
            error_embed = create_error_embed(f"The model '{model_key}' is not currently available.")
            if ctx:
                await ctx.reply(embed=error_embed)
            else:
                await interaction.followup.send(embed=error_embed)
            return
        
        config = available_models[model_key]  # Use already fetched config
        if not config:
            error_embed = create_error_embed(f"Configuration for model '{model_key}' not found.")
            if ctx:
                await ctx.reply(embed=error_embed)
            else:
                await interaction.followup.send(embed=error_embed)
            return
        
        channel = ctx.channel if ctx else (interaction.channel if interaction else reply_msg.channel)
        api_cog = self.bot.get_cog("APIUtils")
        duck_cog = self.bot.get_cog("DuckDuckGo")
        tool_cog = self.bot.get_cog("ToolCalling")
        
        if image_url and not config.get("supports_images", False):
            # Use gpt-4.1-nano to caption the image
            try:
                # Caption the image using gpt-4.1-nano
                caption_prompt = "Please describe this image in detail, focusing on the main subjects, their actions, expressions, and the overall context or scene. Be specific and comprehensive."
                
                # Get API cog first
                if not api_cog:
                    api_cog = self.bot.get_cog("APIUtils")
                
                caption_result, caption_stats = await api_cog.send_request(
                    model="openai/gpt-4.1-nano",
                    message_content=caption_prompt,
                    image_url=image_url,
                    api="openrouter",
                    max_tokens=500
                )
                
                # Add caption cost to user quota
                if caption_stats and caption_stats.get('total_cost', 0) > 0:
                    from user_quotas import quota_manager
                    quota_manager.add_usage(user_id, caption_stats['total_cost'])
                
                # Prepend caption to the original prompt
                image_context = f"[Image Description: {caption_result}]\n\n{prompt}"
                
                # Log the captioning
                logger.info(f"Generated image caption for unsupported model {model_key}: {len(caption_result)} chars")
                
                # Continue with text-only request using the caption
                prompt = image_context
                image_url = None  # Clear image URL since we're now using text
                
                # Notify user about automatic captioning
                notify_embed = discord.Embed(
                    title="Image Captioning",
                    description=f"✨ {config.get('name', model_key)} doesn't support images directly. I've automatically generated a description of your image to include with your request.",
                    color=0x00CED1
                )
                if ctx:
                    await ctx.send(embed=notify_embed, delete_after=10)
                else:
                    await interaction.followup.send(embed=notify_embed, ephemeral=True)
                    
            except Exception as e:
                logger.exception(f"Error captioning image: {e}")
                error_embed = create_error_embed(f"Failed to process the image for {config.get('name', model_key)}. Please try using a model that supports images directly.")
                if ctx:
                    await ctx.reply(embed=error_embed)
                else:
                    await interaction.followup.send(embed=error_embed)
                return

        if not image_url:
            from generic_chat import process_attachments, perform_chat_query, perform_chat_query_with_tools
            final_prompt, img_url = await process_attachments(prompt, attachments or [], is_slash=(interaction is not None))
        else:
            final_prompt = prompt
            img_url = image_url

        cleaned_prompt = final_prompt
        model = config["api_model"]
        footer = config["default_footer"]
        api = config.get("api", "openai")
        
        # Check if model supports tools
        supports_tools = config.get("supports_tools", True)  # Default to True for most models
            
        try:
            # Use tool-enabled query if tools are supported and enabled
            if supports_tools and tool_calling and tool_cog:
                
                # Convert web_search or deep_research flag to force_tools for backward compatibility
                force_tools = web_search or deep_research
                
                # If deep_research is enabled, prepend instruction to use deep research tool
                if deep_research:
                    cleaned_prompt = "Use the deep_research tool to comprehensively investigate: " + cleaned_prompt
                
                result, elapsed, footer_with_stats = await perform_chat_query_with_tools(
                    prompt=cleaned_prompt,
                    api_cog=api_cog,
                    tool_cog=tool_cog,
                    channel=channel,
                    user_id=user_id,
                    duck_cog=duck_cog,
                    image_url=img_url,
                    reference_message=reference_message,
                    model=model,
                    reply_footer=footer,
                    api=api,
                    use_fun=fun,
                    use_tools=tool_calling,
                    force_tools=force_tools,
                    max_tokens=max_tokens,
                    interaction=interaction,
                    deep_research=deep_research,
                    username=username
                )
            else:
                # Fall back to standard query
                result, elapsed, footer_with_stats = await perform_chat_query(
                    prompt=cleaned_prompt,
                    api_cog=api_cog,
                    channel=channel,
                    user_id=user_id,
                    duck_cog=duck_cog,
                    image_url=img_url,
                    reference_message=reference_message,
                    model=model,
                    reply_footer=footer,
                    api=api,
                    use_fun=fun,
                    web_search=web_search,
                    max_tokens=max_tokens,
                    interaction=interaction,
                    username=username
                )
            
            # Check if result contains API error information
            if result and "Error code: 402" in result:
                error_embed = create_error_embed("The AI service has insufficient credits. Please reduce max_tokens or try again later.")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)
            elif result and "there was an error communicating with the AI service:" in result:
                error_embed = create_error_embed(result)
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)

            final_footer = footer_with_stats
                
        except Exception as e:
            logger.exception(f"Error in {model_key} request: %s", e)
            error_embed = create_error_embed(f"Error generating reply: {e}")
            if ctx:
                return await ctx.reply(embed=error_embed)
            else:
                return await interaction.followup.send(embed=error_embed)
            
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=final_footer)
        
        attribution_text = None
        if reply_user and reply_msg:
            if hasattr(reply_msg, 'guild') and reply_msg.guild:
                message_link = f"https://discord.com/channels/{reply_msg.guild.id}/{reply_msg.channel.id}/{reply_msg.id}"
            else:
                message_link = f"https://discord.com/channels/@me/{reply_msg.channel.id}/{reply_msg.id}"
            attribution_text = f"### {reply_user.mention} used AI Reply > {message_link}"

        # Detect fun mode from the original message if it was a bot message
        detected_fun_mode = False
        if reply_msg and reply_msg.author.bot:
            ai_context_menus = self.bot.get_cog("AIContextMenus")
            if ai_context_menus:
                detected_fun_mode = ai_context_menus._detect_fun_mode_from_footer(reply_msg)
                if detected_fun_mode:
                    logger.info("Detected fun mode from original message, updating footer")
                    # Update the embed footer to include fun mode
                    current_footer = embed.footer.text if embed.footer else final_footer
                    if " | Fun Mode" not in current_footer:
                        # Insert fun mode after the model name (first line)
                        lines = current_footer.split('\n')
                        if lines:
                            lines[0] += " | Fun Mode"
                            embed.set_footer(text='\n'.join(lines))

        # Check if this is a context menu reply in a server that should create a thread
        if reply_msg and reply_msg.guild and reply_user and not isinstance(reply_msg.channel, discord.Thread):
            # Generate AI thread name using gpt-4.1-nano
            try:
                original_content = reply_msg.content or "[No text content]"
                if reply_msg.embeds and reply_msg.embeds[0].description:
                    original_content = reply_msg.embeds[0].description
                
                # Prepare content for thread naming (limit for API efficiency)
                user_content = original_content[:200]
                ai_content = result[:200]
                
                name_prompt = f"Generate a short, descriptive thread title (max 50 characters) based on this conversation topic. Return only the title, no explanation:\n\nUser message: {user_content}\nAI response: {ai_content}\n\nThread title:"
                
                api_cog = self.bot.get_cog("APIUtils")
                if api_cog:
                    thread_name, _ = await api_cog.send_request(
                        model="openai/gpt-4.1-nano", 
                        message_content=name_prompt,
                        api="openrouter",
                        max_tokens=20
                    )
                    thread_name = thread_name.strip()[:50]  # Ensure 50 char limit
                else:
                    # Fallback if API not available
                    thread_name = user_content[:47] + "..." if len(user_content) > 47 else user_content
                
                # Create thread from the original message
                thread = await reply_msg.create_thread(name=thread_name or "AI Conversation")
                
                # Send response in the thread
                await send_embed(thread, embed, content=attribution_text)
                
                logger.info(f"Created thread '{thread_name}' for AI conversation")
                
            except Exception as e:
                logger.error(f"Failed to create thread: {e}")
                # Fallback to normal reply if thread creation fails
                await send_embed(reply_msg.channel, embed, reply_to=reply_msg, content=attribution_text)
        elif reply_msg and isinstance(reply_msg.channel, discord.Thread):
            # Already in a thread, check if we should continue fun mode
            # Look through thread history to detect if fun mode was used
            thread_fun_mode = False
            try:
                async for message in reply_msg.channel.history(limit=20):
                    if message.author.bot and message.embeds:
                        ai_context_menus = self.bot.get_cog("AIContextMenus")
                        if ai_context_menus and ai_context_menus._detect_fun_mode_from_footer(message):
                            thread_fun_mode = True
                            logger.info(f"Detected fun mode in thread history, continuing with fun mode")
                            break
            except Exception as e:
                logger.warning(f"Failed to check thread history for fun mode: {e}")
            
            # Update embed footer if thread was using fun mode
            if thread_fun_mode and embed.footer:
                current_footer = embed.footer.text
                if " | Fun Mode" not in current_footer:
                    lines = current_footer.split('\n')
                    if lines:
                        lines[0] += " | Fun Mode"
                        embed.set_footer(text='\n'.join(lines))
            
            # Send as a reply without attribution text
            channel_name = getattr(reply_msg.channel, 'name', f'Channel {reply_msg.channel.id}') if reply_msg.channel else 'None channel'
            logger.info(f"Sending response to thread: {channel_name}")
            if reply_msg.channel:
                await send_embed(reply_msg.channel, embed, reply_to=reply_msg)
            else:
                logger.error("reply_msg.channel is None, cannot send response")
                return
        elif ctx or reply_msg:
            channel = ctx.channel if ctx else reply_msg.channel
            message_to_reply = ctx.message if ctx else reply_msg
            await send_embed(channel, embed, reply_to=message_to_reply, content=attribution_text)
        else:
            # Handle /thread command thread creation
            if create_thread and interaction and interaction.guild:
                thread_created = False
                try:
                    # Generate AI thread name
                    user_content = prompt[:200]
                    ai_content = result[:200]
                    
                    name_prompt = f"Generate a short, descriptive thread title (max 50 characters) based on this conversation topic. Return only the title, no explanation:\n\nUser message: {user_content}\nAI response: {ai_content}\n\nThread title:"
                    
                    api_cog = self.bot.get_cog("APIUtils")
                    if api_cog:
                        thread_name, _ = await api_cog.send_request(
                            model="openai/gpt-4.1-nano", 
                            message_content=name_prompt,
                            api="openrouter",
                            max_tokens=20
                        )
                        thread_name = thread_name.strip()[:50]  # Ensure 50 char limit
                    else:
                        # Fallback if API not available
                        thread_name = user_content[:47] + "..." if len(user_content) > 47 else user_content
                    
                    # Send the AI response to the channel first
                    bot_message = await send_embed(interaction.channel, embed, content=attribution_text)
                    
                    # Create thread from the bot's response message
                    if bot_message:
                        thread = await bot_message.create_thread(
                            name=thread_name or "AI Conversation",
                            auto_archive_duration=1440  # 24 hours
                        )
                        logger.info(f"Created thread '{thread_name}' from /thread command")
                        thread_created = True
                    
                    # Send minimal ephemeral response to satisfy Discord interaction requirement
                    if thread_created:
                        await interaction.followup.send("✅ Thread created successfully.", ephemeral=True)
                    else:
                        await interaction.followup.send("⚠️ Thread creation failed, but here's your AI response above.", ephemeral=True)
                    
                except Exception as e:
                    logger.error(f"Failed to create thread from /thread command: {e}")
                    error_embed = create_error_embed(f"Failed to create thread: {str(e)}")
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                
                # If thread wasn't created, we still need to ensure interaction response was sent
                if not thread_created:
                    logger.warning("Thread creation failed but AI response was sent to channel")
            else:
                await send_embed(interaction.channel, embed, interaction=interaction, content=attribution_text)

    
    @app_commands.command(name="chat", description="Chat with an AI model")
    @app_commands.describe(
        prompt="Your query or instructions",
        model="Model to use for the response",
        fun="Toggle fun mode",
        web_search="Force web search (requires tool_calling)",
        deep_research="Force deep research mode",
        tool_calling="Enable AI to use tools like web search and content retrieval",
        attachment="Optional attachment (image or text file)",
        max_tokens="Maximum tokens for response (default: 8000)"
    )
    async def chat_slash(
        self, 
        interaction: Interaction, 
        prompt: str,
        model: ModelChoices = DEFAULT_MODEL, 
        fun: bool = False,
        web_search: bool = False,
        deep_research: bool = False,
        tool_calling: bool = True,
        attachment: Optional[Attachment] = None,
        max_tokens: Optional[int] = None
    ):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        username = interaction.user.name
        formatted_prompt = f"{username}: {prompt}"
        
        has_image = False
        if attachment:
            has_image = attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
        
        model_config = self._get_model_config(model)
        if has_image and model_config and not model_config.get("supports_images", False):
            default_model_config = self._get_model_config(DEFAULT_MODEL)
            default_model_name = default_model_config.get('name', DEFAULT_MODEL) if default_model_config else DEFAULT_MODEL
            await interaction.followup.send(
                f"⚠️ Automatically switched to {default_model_name} because you attached an image " 
                f"and {model_config.get('name', model)} doesn't support image processing.",
                ephemeral=True
            )
            model = DEFAULT_MODEL
        
        await self._process_ai_request(formatted_prompt, model, interaction=interaction, attachments=attachments, fun=fun, web_search=web_search, deep_research=deep_research, tool_calling=tool_calling, max_tokens=max_tokens or 8000)
    
    @app_commands.command(name="thread", description="Chat with an AI model and create a thread from the response")
    @app_commands.describe(
        prompt="Your query or instructions",
        model="Model to use for the response",
        fun="Toggle fun mode",
        web_search="Force web search (requires tool_calling)",
        deep_research="Force deep research mode",
        tool_calling="Enable AI to use tools like web search and content retrieval",
        attachment="Optional attachment (image or text file)",
        max_tokens="Maximum tokens for response (default: 8000)"
    )
    async def thread_slash(
        self, 
        interaction: Interaction, 
        prompt: str,
        model: ModelChoices = DEFAULT_MODEL, 
        fun: bool = False,
        web_search: bool = False,
        deep_research: bool = False,
        tool_calling: bool = True,
        attachment: Optional[Attachment] = None,
        max_tokens: Optional[int] = None
    ):
        # Check if we're in a guild channel that supports threads
        if not interaction.guild or isinstance(interaction.channel, discord.Thread):
            error_embed = create_error_embed("Threads can only be created in server text channels (not in DMs or existing threads).")
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        username = interaction.user.name
        formatted_prompt = f"{username}: {prompt}"
        
        has_image = False
        if attachment:
            has_image = attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
        
        model_config = self._get_model_config(model)
        if has_image and model_config and not model_config.get("supports_images", False):
            default_model_config = self._get_model_config(DEFAULT_MODEL)
            default_model_name = default_model_config.get('name', DEFAULT_MODEL) if default_model_config else DEFAULT_MODEL
            await interaction.followup.send(
                f"⚠️ Automatically switched to {default_model_name} because you attached an image " 
                f"and {model_config.get('name', model)} doesn't support image processing.",
                ephemeral=True
            )
            model = DEFAULT_MODEL
        
        # Process the AI request with a special flag to create thread
        await self._process_ai_request(
            formatted_prompt, 
            model, 
            interaction=interaction, 
            attachments=attachments, 
            fun=fun, 
            web_search=web_search, 
            deep_research=deep_research, 
            tool_calling=tool_calling, 
            max_tokens=max_tokens or 8000,
            create_thread=True  # New parameter to signal thread creation
        )

class AIContextMenus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _detect_model_from_footer(self, message: discord.Message) -> Optional[str]:
        """Detect which model was used based on the message footer"""
        if not message.author.bot or not message.embeds:
            return None
        
        embed = message.embeds[0]
        if not embed.footer or not embed.footer.text:
            return None
        
        # The footer format has model name on the first line
        footer_text = embed.footer.text
        first_line = footer_text.split('\n')[0].strip()
        
        logger.info(f"Detecting model from footer: '{first_line}'")
        
        # Map footer names back to model keys
        for model_key, config in MODELS_CONFIG.items():
            if config.get("default_footer") == first_line or config.get("name") == first_line:
                logger.info(f"Detected model: {model_key}")
                return model_key
        
        logger.warning(f"Could not detect model from footer: '{first_line}'")
        return None
    
    def _detect_fun_mode_from_footer(self, message: discord.Message) -> bool:
        """Detect if fun mode was used based on the message footer"""
        if not message.author.bot or not message.embeds:
            return False
        
        embed = message.embeds[0]
        if not embed.footer or not embed.footer.text:
            return False
        
        # The footer format has model name on the first line
        footer_text = embed.footer.text
        first_line = footer_text.split('\n')[0].strip()
        
        # Check if "Fun Mode" is in the first line
        is_fun = "Fun Mode" in first_line
        logger.info(f"Detecting fun mode from footer: '{first_line}' -> {is_fun}")
        return is_fun
        
    class ModelSelectModal(discord.ui.Modal):
        additional_input = discord.ui.TextInput(
            label="Additional Input (Optional)",
            style=discord.TextStyle.long,
            required=False,
            placeholder="Add any extra context or instructions..."
        )
        
        def __init__(self, reference_message, original_message, channel, detected_model=None):
            self.reference_message = reference_message
            self.original_message = original_message
            self.channel = channel
            self.detected_model = detected_model
            
            self.has_image = self._check_for_images(original_message)
            
            title = "AI Reply" + (" (Image detected)" if self.has_image else "")
            super().__init__(title=title)
        
        def _check_for_images(self, message):
            if message.attachments:
                return any(att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) 
                        for att in message.attachments)
            return False
            
        async def on_submit(self, interaction: discord.Interaction):
            additional_text = self.additional_input.value or ""
            username = interaction.user.name
            formatted_prompt = f"{username}: {additional_text}"

            view = ModelSelectionView(
                has_image=self.has_image,
                reference_message=self.reference_message,
                original_message=self.original_message,
                additional_text=formatted_prompt,
                user_id=interaction.user.id,
                detected_model=self.detected_model
            )
            # Store bot reference for model availability check
            view._bot_ref = interaction.client
            # Store interaction reference for deletion
            view._modal_interaction = interaction
            # Refresh dropdown now that we have bot reference
            view.clear_items()
            view._create_dropdown()
            view._create_buttons()
            
            await interaction.response.send_message(
                "Please select an AI model and click Submit:",
                view=view,
                ephemeral=True
            )


class ModelSelectionView(discord.ui.View):
    def __init__(self, has_image, reference_message, original_message, additional_text, user_id=None, detected_model=None):
        super().__init__(timeout=120)
        self.has_image = has_image
        self.reference_message = reference_message
        self.original_message = original_message
        self.additional_text = additional_text
        self.user_id = user_id
        self.selected_model = detected_model if detected_model else DEFAULT_MODEL
        
        # Detect fun mode from original message footer if it's a bot message
        self.fun = False
        if original_message and original_message.author.bot and original_message.embeds:
            embed = original_message.embeds[0]
            if embed.footer and embed.footer.text and "Fun Mode" in embed.footer.text:
                self.fun = True
                logger.info("Detected fun mode from original message footer")
        
        self.web_search = False
        self.deep_research = False
        self.tool_calling = True
        
        self._create_dropdown()
        self._create_buttons()
    
    def _create_dropdown(self):
        options = []
        
        # Get available models for this user
        available_models_dict = {}
        if hasattr(self, '_bot_ref') and self._bot_ref:
            ai_commands = self._bot_ref.get_cog("AICommands")
            if ai_commands:
                available_models_dict = ai_commands._get_available_models(self.user_id or 0)
        else:
            # Fallback to all enabled models if no bot reference
            available_models_dict = {k: v for k, v in MODELS_CONFIG.items() if v.get('enabled', False)}
        
        # Add image-supporting models first if we have an image
        if self.has_image:
            for model_key, model_config in available_models_dict.items():
                if model_config.get("supports_images", False):
                    options.append(discord.SelectOption(
                        label=model_config.get("name", model_key),
                        value=model_key,
                        description=f"Supports images | {model_config.get('name', model_key)}",
                        default=self.selected_model == model_key
                    ))
        else:
            # Add all available models if no image
            for model_key, model_config in available_models_dict.items():
                options.append(discord.SelectOption(
                    label=model_config.get("name", model_key),
                    value=model_key,
                    description=model_config.get("name", model_key),
                    default=self.selected_model == model_key
                ))
        
        if not options:
            options.append(discord.SelectOption(
                label="No models available",
                value="none",
                description="No models are currently available"
            ))
        
        self.model_select = discord.ui.Select(
            placeholder="Choose AI model",
            options=options
        )
        self.model_select.callback = self.on_model_select
        self.add_item(self.model_select)
    
    def _create_buttons(self):
        fun_button = discord.ui.Button(
            label=f"Fun Mode: {'ON' if self.fun else 'OFF'}", 
            style=discord.ButtonStyle.secondary, 
            custom_id="toggle_fun"
        )
        fun_button.callback = self.toggle_fun
        self.add_item(fun_button)
        
        tool_button = discord.ui.Button(
            label=f"Tools: {'ON' if self.tool_calling else 'OFF'}", 
            style=discord.ButtonStyle.secondary, 
            custom_id="toggle_tools"
        )
        tool_button.callback = self.toggle_tools
        self.add_item(tool_button)
        
        web_search_button = discord.ui.Button(
            label=f"Force Search: {'ON' if self.web_search else 'OFF'}", 
            style=discord.ButtonStyle.secondary, 
            custom_id="toggle_web_search"
        )
        web_search_button.callback = self.toggle_web_search
        self.add_item(web_search_button)
        
        deep_research_button = discord.ui.Button(
            label=f"Deep Research: {'ON' if self.deep_research else 'OFF'}", 
            style=discord.ButtonStyle.secondary, 
            custom_id="toggle_deep_research"
        )
        deep_research_button.callback = self.toggle_deep_research
        self.add_item(deep_research_button)
        
        submit_button = discord.ui.Button(
            label="Submit",
            style=discord.ButtonStyle.primary,
            custom_id="submit_button"
        )
        submit_button.callback = self.submit_button_callback
        self.add_item(submit_button)
    
    async def on_model_select(self, interaction: discord.Interaction):
        self.selected_model = self.model_select.values[0]
        
        # Check if selected model supports images when image is present
        if self.has_image and hasattr(self, '_bot_ref') and self._bot_ref:
            ai_commands = self._bot_ref.get_cog("AICommands")
            if ai_commands:
                model_config = ai_commands._get_model_config(self.selected_model)
                if model_config and not model_config.get("supports_images", False):
                    await interaction.response.send_message(
                        f"Warning: {model_config.get('name', self.selected_model)} doesn't support images. Please select a model that supports image processing.",
                        ephemeral=True
                    )
                    return
        
        await interaction.response.defer()
    
    async def toggle_fun(self, interaction: discord.Interaction):
        self.fun = not self.fun
        self.clear_items()
        self._create_dropdown()
        self._create_buttons()
        await interaction.response.edit_message(view=self)
    
    async def toggle_tools(self, interaction: discord.Interaction):
        self.tool_calling = not self.tool_calling
        # If tools are disabled, also disable web search and deep research
        if not self.tool_calling:
            self.web_search = False
            self.deep_research = False
        self.clear_items()
        self._create_dropdown()
        self._create_buttons()
        await interaction.response.edit_message(view=self)
    
    async def toggle_web_search(self, interaction: discord.Interaction):
        self.web_search = not self.web_search
        # If web search is enabled, ensure tools are also enabled
        if self.web_search:
            self.tool_calling = True
        self.clear_items()
        self._create_dropdown()
        self._create_buttons()
        await interaction.response.edit_message(view=self)
    
    async def toggle_deep_research(self, interaction: discord.Interaction):
        self.deep_research = not self.deep_research
        # If deep research is enabled, ensure tools are also enabled
        if self.deep_research:
            self.tool_calling = True
        self.clear_items()
        self._create_dropdown()
        self._create_buttons()
        await interaction.response.edit_message(view=self)
    
    async def submit_button_callback(self, interaction: discord.Interaction):
        # Defer with ephemeral response to avoid cluttering the channel
        await interaction.response.defer(ephemeral=True)
        
        model_key = self.selected_model
        
        image_url = None
        if self.has_image:
            for att in self.original_message.attachments:
                if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    image_url = att.url
                    logger.info(f"Found image attachment: {image_url}")
                    break
        
        ai_commands = interaction.client.get_cog("AICommands")
        if not ai_commands:
            await interaction.followup.send("AI commands not available", ephemeral=True)
            return
        
        try:            
            logger.info(f"Submitting AI request with model: {model_key}, has_image: {self.has_image}, image_url: {image_url}")
            
            await ai_commands._process_ai_request(
                prompt=self.additional_text,
                model_key=model_key,
                interaction=interaction,
                reference_message=self.reference_message,
                image_url=image_url,
                reply_msg=self.original_message,
                fun=self.fun,
                web_search=self.web_search,
                deep_research=self.deep_research,
                tool_calling=self.tool_calling,
                reply_user=interaction.user
            )
            
            # Delete the ephemeral message from the modal submission
            try:
                if hasattr(self, '_modal_interaction') and self._modal_interaction:
                    await self._modal_interaction.delete_original_response()
                else:
                    # Fallback: try to delete the current interaction response
                    await interaction.delete_original_response()
            except discord.HTTPException as e:
                logger.warning(f"Could not delete ephemeral message: {e}")
            
        except Exception as e:
            logger.exception(f"Error processing AI request: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


@app_commands.context_menu(name="AI Reply")
async def ai_context_menu(interaction: Interaction, message: discord.Message):
    # Get the AIContextMenus cog to access detection method
    ai_context_cog = interaction.client.get_cog("AIContextMenus")
    detected_model = None
    
    if ai_context_cog and message.author == interaction.client.user:
        # Try to detect the model from the bot's own message footer
        detected_model = ai_context_cog._detect_model_from_footer(message)
        if detected_model:
            logger.info(f"Context menu detected model '{detected_model}' from bot message")
        content = message.embeds[0].description.strip() if message.embeds and message.embeds[0].description else ""
    else:
        content = message.content
    
    has_images = False
    for att in message.attachments:
        if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            has_images = True
            break
    
    reference_message = f"{message.author.name}: {content}"
    if has_images:
        reference_message += " [This message contains an image attachment]"
    
    modal = AIContextMenus.ModelSelectModal(reference_message, message, interaction.channel, detected_model)
    await interaction.response.send_modal(modal)

@app_commands.context_menu(name="Generate with Image")
async def edit_image_context_menu(interaction: Interaction, message: discord.Message):
    # Count images in message
    image_count = 0
    
    # Check attachments
    for att in message.attachments:
        if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            image_count += 1
    
    # Check embeds for images
    for embed in message.embeds:
        if embed.image:
            image_count += 1
    
    if image_count == 0:
        await interaction.response.send_message(
            "This message doesn't contain any images to use.",
            ephemeral=True
        )
        return
    
    # Show multi-image feedback but continue to modal
    if image_count > 1:
        # We'll send the modal and let the user know about multiple images in the title
        pass
    
    # Get the ImageGen cog to access the modal
    image_cog = interaction.client.get_cog("ImageGen")
    if not image_cog:
        await interaction.response.send_message(
            "Image editing functionality is not available.",
            ephemeral=True
        )
        return
    
    # Import the modal class from image_gen
    from .image_gen import ImageEditModal
    modal = ImageEditModal(image_cog, message)
    await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(AICommands(bot))
    await bot.add_cog(AIContextMenus(bot))
    
    bot.tree.add_command(ai_context_menu)
    bot.tree.add_command(edit_image_context_menu)