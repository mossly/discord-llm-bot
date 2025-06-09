import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from typing import Optional, Literal
from embed_utils import send_embed

logger = logging.getLogger(__name__)


class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _get_model_config(self, model_key: str) -> dict:
        """Get configuration for a specific model"""
        model_management = self.bot.get_cog("ModelManagement")
        if model_management and model_key in model_management.models_config:
            return model_management.models_config[model_key]
        else:
            # No fallback - models must be configured in models_config.json
            return {}
    
    def _get_available_models(self, user_id: int) -> list:
        """Get list of available model keys for a user"""
        model_management = self.bot.get_cog("ModelManagement")
        if model_management:
            available_models = model_management.get_available_models(user_id)
            return list(available_models.keys())
        else:
            # No fallback - return empty list if model management is not available
            return []
    
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
        
        config = self._get_model_config(model_key)
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
                description="Image attachments only supported with GPT-4o-mini",
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
                    max_tokens=max_tokens
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
                    max_tokens=max_tokens
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
            
        embed = discord.Embed(title="", description=result, color=config["color"])
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

    async def model_autocomplete(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete function for model parameter"""
        available_models = self._get_available_models(interaction.user.id)
        choices = []
        
        for model_key in available_models:
            if current.lower() in model_key.lower():
                config = self._get_model_config(model_key)
                if config:
                    name = config.get("name", model_key)
                    choices.append(app_commands.Choice(name=f"{model_key} - {name}", value=model_key))
                
        return choices[:25]  # Discord limits to 25 choices
    
    @app_commands.command(name="chat", description="Chat with an AI model")
    @app_commands.describe(
        model="Model to use for the response (type model name)",
        fun="Toggle fun mode",
        web_search="Force web search (requires tool_calling)",
        tool_calling="Enable AI to use tools like web search and content retrieval",
        prompt="Your query or instructions",
        attachment="Optional attachment (image or text file)",
        max_tokens="Maximum tokens for response (default: 8000)"
    )
    @app_commands.autocomplete(model=model_autocomplete)
    async def chat_slash(
        self, 
        interaction: Interaction, 
        model: str,
        prompt: str, 
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
                f"⚠️ Automatically switched to GPT-4o-mini because you attached an image " 
                f"and {model_config.get('name', model)} doesn't support image processing.",
                ephemeral=True
            )
            model = "gpt-4o-mini"
        
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
        self.selected_model = "gpt-4o-mini" if has_image else "gpt-o3-mini"
        self.fun = False
        self.web_search = False
        self.tool_calling = True
        
        self._create_dropdown()
        self._create_buttons()
    
    def _create_dropdown(self):
        options = []
        
        # Get available models for this user
        # We need to get the bot instance to access the AICommands cog
        if hasattr(self, '_bot_ref') and self._bot_ref:
            ai_commands = self._bot_ref.get_cog("AICommands")
            if ai_commands:
                available_models = ai_commands._get_available_models(self.user_id or 0)
            else:
                available_models = []
        else:
            # No bot reference available - no models available
            available_models = []
        
        # Get model configurations from the model management system
        model_management = None
        if hasattr(self, '_bot_ref') and self._bot_ref:
            model_management = self._bot_ref.get_cog("ModelManagement")
        
        # Get available models dict instead of just keys
        available_models_dict = {}
        if hasattr(self, '_bot_ref') and self._bot_ref:
            ai_commands = self._bot_ref.get_cog("AICommands")
            if ai_commands:
                model_management = ai_commands.bot.get_cog("ModelManagement")
                if model_management:
                    available_models_dict = model_management.get_available_models(self.user_id or 0)
        
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
        
        if self.has_image and self.selected_model != "gpt-4o-mini":
            await interaction.response.send_message(
                "Warning: Only GPT-4o-mini can process images. Using other models will ignore the image.",
                ephemeral=True
            )
        else:
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