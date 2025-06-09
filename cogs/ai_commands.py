import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from typing import Optional, Literal
from embed_utils import send_embed
import os

logger = logging.getLogger(__name__)

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
        "api_model": "openai/o4-mini",
        "supports_images": False,
        "supports_tools": True,
        "api": "openrouter",
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
    
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None, attachments=None, reference_message=None, image_url=None, reply_msg: Optional[discord.Message] = None, fun: bool = False, web_search: bool = False, tool_calling: bool = True, reply_user=None, max_tokens: int = 8000):
        # Get user ID for quota tracking and model availability check
        if ctx:
            user_id = str(ctx.author.id)
            user_id_int = ctx.author.id
        elif interaction:
            user_id = str(interaction.user.id)
            user_id_int = interaction.user.id
        elif reply_user:
            user_id = str(reply_user.id)
            user_id_int = reply_user.id
        else:
            user_id = "unknown"
            user_id_int = 0
        
        # Check if model is available to this user
        available_models = self._get_available_models(user_id_int)
        if model_key not in available_models:
            error_embed = discord.Embed(
                title="Model Not Available",
                description=f"The model '{model_key}' is not currently available.",
                color=0xDC143C
            )
            if ctx:
                await ctx.reply(embed=error_embed)
            else:
                await interaction.followup.send(embed=error_embed)
            return
        
        config = available_models[model_key]  # Use already fetched config
        if not config:
            error_embed = discord.Embed(
                title="Model Configuration Error",
                description=f"Configuration for model '{model_key}' not found.",
                color=0xDC143C
            )
            if ctx:
                await ctx.reply(embed=error_embed)
            else:
                await interaction.followup.send(embed=error_embed)
            return
        
        channel = ctx.channel if ctx else interaction.channel
        api_cog = self.bot.get_cog("APIUtils")
        duck_cog = self.bot.get_cog("DuckDuckGo")
        tool_cog = self.bot.get_cog("ToolCalling")
        
        if image_url and not config.get("supports_images", False):
            error_embed = discord.Embed(
                title="ERROR",
                description=f"Image attachments are not supported by {config.get('name', model_key)}. Please use a model that supports images.",
                color=0xDC143C
            )
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
                
                # Convert web_search flag to force_tools for backward compatibility
                force_tools = web_search
                
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
                    interaction=interaction
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
                    interaction=interaction
                )
            
            # Check if result contains API error information
            if result and "Error code: 402" in result:
                error_embed = discord.Embed(
                    title="API Quota Exceeded", 
                    description="The AI service has insufficient credits. Please reduce max_tokens or try again later.",
                    color=0xDC143C
                )
                error_embed.set_footer(text="Error: Insufficient API credits")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)
            elif result and "there was an error communicating with the AI service:" in result:
                error_embed = discord.Embed(
                    title="API Error", 
                    description=result,
                    color=0xDC143C
                )
                error_embed.set_footer(text="AI Service Error")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)

            final_footer = footer_with_stats
                
        except Exception as e:
            logger.exception(f"Error in {model_key} request: %s", e)
            error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
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

        if ctx or reply_msg:
            channel = ctx.channel if ctx else reply_msg.channel
            message_to_reply = ctx.message if ctx else reply_msg
            await send_embed(channel, embed, reply_to=message_to_reply, content=attribution_text)
        else:
            await send_embed(interaction.channel, embed, interaction=interaction, content=attribution_text)

    
    @app_commands.command(name="chat", description="Chat with an AI model")
    @app_commands.describe(
        prompt="Your query or instructions",
        model="Model to use for the response",
        fun="Toggle fun mode",
        web_search="Force web search (requires tool_calling)",
        tool_calling="Enable AI to use tools like web search and content retrieval",
        attachment="Optional attachment (image or text file)",
        max_tokens="Maximum tokens for response (default: 8000)"
    )
    async def chat_slash(
        self, 
        interaction: Interaction, 
        prompt: str,
        model: ModelChoices = "gemini-2.5-flash-preview", 
        fun: bool = False,
        web_search: bool = False,
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
            await interaction.followup.send(
                f"⚠️ Automatically switched to Gemini 2.5 Flash because you attached an image " 
                f"and {model_config.get('name', model)} doesn't support image processing.",
                ephemeral=True
            )
            model = "gemini-2.5-flash-preview"
        
        await self._process_ai_request(formatted_prompt, model, interaction=interaction, attachments=attachments, fun=fun, web_search=web_search, tool_calling=tool_calling, max_tokens=max_tokens or 8000)

class AIContextMenus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    class ModelSelectModal(discord.ui.Modal):
        additional_input = discord.ui.TextInput(
            label="Additional Input (Optional)",
            style=discord.TextStyle.long,
            required=False,
            placeholder="Add any extra context or instructions..."
        )
        
        def __init__(self, reference_message, original_message, channel):
            self.reference_message = reference_message
            self.original_message = original_message
            self.channel = channel
            
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
                user_id=interaction.user.id
            )
            # Store bot reference for model availability check
            view._bot_ref = interaction.client
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
    def __init__(self, has_image, reference_message, original_message, additional_text, user_id=None):
        super().__init__(timeout=120)
        self.has_image = has_image
        self.reference_message = reference_message
        self.original_message = original_message
        self.additional_text = additional_text
        self.user_id = user_id
        self.selected_model = "gemini-2.5-flash-preview"
        self.fun = False
        self.web_search = False
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
        # If tools are disabled, also disable web search
        if not self.tool_calling:
            self.web_search = False
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
    
    async def submit_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)
        
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
                tool_calling=self.tool_calling,
                reply_user=interaction.user
            )
            
            try:
                await interaction.delete_original_response()
            except discord.HTTPException as e:
                logger.warning(f"Could not delete original response: {e}")
            
        except Exception as e:
            logger.exception(f"Error processing AI request: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


@app_commands.context_menu(name="AI Reply")
async def ai_context_menu(interaction: Interaction, message: discord.Message):
    if message.author == interaction.client.user:
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
    
    modal = AIContextMenus.ModelSelectModal(reference_message, message, interaction.channel)
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