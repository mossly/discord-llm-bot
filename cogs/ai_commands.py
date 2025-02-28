import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from typing import Optional, Literal
from embed_utils import send_embed
from status_utils import update_status

logger = logging.getLogger(__name__)

# Enhanced model configuration with more details
MODEL_CONFIG = {
    "gpt-o3-mini": {
        "name": "GPT-o3-mini",
        "function": "perform_chat_query",
        "color": 0x32a956,
        "default_model": "o3-mini",
        "default_footer": "o3-mini | default",
        "api_model": "o3-mini",
        "system_prompt": "Use markdown formatting.",
        "supports_images": False
    },
    "gpt-4o-mini": {
        "name": "GPT-4o-mini",
        "function": "perform_chat_query",
        "color": 0x32a956,
        "default_model": "gpt-4o-mini",
        "default_footer": "gpt-4o-mini | default",
        "api_model": "gpt-4o-mini",
        "system_prompt": "Use markdown formatting.",
        "supports_images": True
    },
    "deepseek": {
        "name": "Deepseek",
        "function": "perform_chat_query",
        "color": 0x32a956, 
        "default_model": "deepseek/deepseek-chat",
        "default_footer": "Deepseek",
        "api_model": "deepseek/deepseek-chat",
        "system_prompt": "Use markdown formatting.",
        "supports_images": False
    },
    "fun": {
        "name": "Fun Mode",
        "function": "perform_fun_query",
        "color": 0x32a956,
        "default_model": "deepseek/deepseek-chat",
        "default_footer": "Deepseek V3 (Fun Mode)",
        "api_model": "deepseek/deepseek-chat",
        "system_prompt": None,
        "supports_images": False
    }
}

class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None,attachments=None, reference_message=None, image_url=None, reply_msg: Optional[discord.Message] = None):
        """Unified handler for all AI requests regardless of command type"""
        config = MODEL_CONFIG[model_key]
        channel = ctx.channel if ctx else interaction.channel
        api_cog = self.bot.get_cog("APIUtils")
        duck_cog = self.bot.get_cog("DuckDuckGo")
        
        if config["function"] == "perform_chat_query":
            from generic_chat import prepare_chat_parameters, perform_chat_query, extract_suffixes
            
            # Check for direct image_url parameter (from context menu)
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
            
            # Process attachments only if no direct image_url was provided
            if not image_url:
                # Process attachments and extract image URL if present
                is_slash = interaction is not None
                from generic_chat import process_attachments
                final_prompt, img_url = await process_attachments(prompt, attachments or [], is_slash=is_slash)
            else:
                # If image_url was directly provided, use it
                final_prompt = prompt
                img_url = image_url
                    
            # Check for suffixes that might override model settings
            cleaned_prompt, model_override, reply_mode, reply_footer = extract_suffixes(final_prompt)
            
            # Decide which model to use (suffix overrides config)
            if model_override != "o3-mini":  # A suffix was detected
                model = model_override
                footer = reply_footer
                system_prompt = reply_mode
            else:
                model = config["api_model"]
                footer = config["default_footer"]
                system_prompt = config["system_prompt"]
                
            try:
                # For text commands (using ctx), use status updates
                # For slash commands (using interaction), the "thinking" state is already set
                if ctx:
                    status_msg = await update_status(None, "...generating reply...", channel=channel)
                    try:
                        result, elapsed, _ = await perform_chat_query(
                            prompt=cleaned_prompt,
                            api_cog=api_cog,
                            channel=channel,
                            duck_cog=duck_cog,
                            image_url=img_url,
                            reference_message=reference_message,
                            model=model,
                            reply_mode=system_prompt,
                            reply_footer=footer,
                            show_status=False  # Don't show status again in the function
                        )
                    finally:
                        from message_utils import delete_msg
                        await delete_msg(status_msg)
                else:  # Slash command
                    result, elapsed, _ = await perform_chat_query(
                        prompt=cleaned_prompt,
                        api_cog=api_cog,
                        channel=channel,
                        duck_cog=duck_cog,
                        image_url=img_url,
                        reference_message=reference_message,
                        model=model,
                        reply_mode=system_prompt,
                        reply_footer=footer,
                        show_status=False  # Don't show status, Discord's "thinking" state is used
                    )
                final_footer = footer
            except Exception as e:
                logger.exception(f"Error in {model_key} request: %s", e)
                error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                error_embed.set_footer(text=f"Error generating reply: {e}")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)


        # Create and send the response embed
        embed = discord.Embed(title="", description=result, color=config["color"])
        embed.set_footer(text=f"{final_footer} | generated in {elapsed} seconds")
        
        # Use the "reply message" (if provided) as the message to reply to.
        if ctx or reply_msg:
            channel = ctx.channel if ctx else reply_msg.channel
            message_to_reply = ctx.message if ctx else reply_msg
            await send_embed(channel, embed, reply_to=message_to_reply)
        else:
            await interaction.followup.send(embed=embed)
        
        # Normalize model name and validate
        model_key = model.lower()
        if model_key not in MODEL_CONFIG:
            await ctx.reply(f"Unknown model '{model}'. Available models: {', '.join(MODEL_CONFIG.keys())}")
            return
            
        await self._process_ai_request(prompt, model_key, ctx=ctx, attachments=ctx.message.attachments)
        
    # ===== SLASH COMMANDS =====
    @app_commands.command(name="fun", description="Fun mode chat - provide a prompt and optionally attach content")
    async def fun_slash(self, interaction: Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        await self._process_ai_request(prompt, "fun", interaction=interaction, attachments=None)

    @app_commands.command(name="chat", description="Select a model and provide a prompt")
    @app_commands.describe(
        model="Model to use for the response",
        prompt="Your query or instructions",
        attachment="Optional attachment (image or text file)"
    )
    async def chat_slash(
        self, 
        interaction: Interaction, 
        model: Literal["gpt-o3-mini", "gpt-4o-mini", "deepseek", "fun"],
        prompt: str, 
        attachment: Optional[Attachment] = None
    ):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, model, interaction=interaction, attachments=attachments)

class AIContextMenus(commands.Cog):
    """Separate cog for context menu commands"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    # Base modal class with model selection
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
            """Check if the message contains image attachments"""
            if message.attachments:
                return any(att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) 
                           for att in message.attachments)
            return False
            
        async def on_submit(self, interaction: discord.Interaction):
            # Get the additional text input
            additional_text = self.additional_input.value or ""
            
            # Create and show model selection view
            view = ModelSelectionView(
                has_image=self.has_image,
                reference_message=self.reference_message,
                original_message=self.original_message,
                additional_text=additional_text
            )
            
            await interaction.response.send_message(
                "Please select an AI model and click Submit:",
                view=view,
                ephemeral=True
            )


class ModelSelectionView(discord.ui.View):
    def __init__(self, has_image, reference_message, original_message, additional_text):
        super().__init__(timeout=120)
        self.has_image = has_image
        self.reference_message = reference_message
        self.original_message = original_message
        self.additional_text = additional_text
        self.selected_model = "gpt-4o-mini" if has_image else "gpt-o3-mini"
        
        # Add the model dropdown
        options = []
        
        # Always include GPT-4o-mini as an option
        options.append(discord.SelectOption(
            label="GPT-4o-mini", 
            value="gpt-4o-mini",
            description="OpenAI model with image support",
            default=self.has_image  # Make it the default if images are present
        ))
        
        # Only add other models if no images are present
        if not self.has_image:
            options.extend([
                discord.SelectOption(
                    label="GPT-o3-mini", 
                    value="gpt-o3-mini", 
                    description="OpenAI standard model",
                    default=True  # Make this the default if no images
                ),
                discord.SelectOption(
                    label="Deepseek", 
                    value="deepseek", 
                    description="Deepseek standard model"
                ),
                discord.SelectOption(
                    label="Fun Mode", 
                    value="fun", 
                    description="Deepseek with fun personality"
                )
            ])
        
        self.model_select = discord.ui.Select(
            placeholder="Choose AI model",
            options=options
        )
        
        # Set up callback for selection changes - just stores the value, doesn't trigger generation
        self.model_select.callback = self.on_model_select
        
        # Add the select to the view
        self.add_item(self.model_select)
        
        # Add the submit button to the view
        submit_button = discord.ui.Button(
            label="Submit",
            style=discord.ButtonStyle.primary,
            custom_id="submit_button"
        )
        submit_button.callback = self.submit_button_callback
        self.add_item(submit_button)
    
    async def on_model_select(self, interaction: discord.Interaction):
        """Store the selected model value without triggering generation"""
        self.selected_model = self.model_select.values[0]
        
        # If user selected a non-4o model for an image, show warning
        if self.has_image and self.selected_model != "gpt-4o-mini":
            await interaction.response.send_message(
                "Warning: Only GPT-4o-mini can process images. Using other models will ignore the image.",
                ephemeral=True
            )
        else:
            # Just acknowledge the selection without further action
            await interaction.response.defer()
    
    async def submit_button_callback(self, interaction: discord.Interaction):
        """Process the submission with the selected model"""
        await interaction.response.defer(thinking=True)
        
        model_key = self.selected_model
        
        # Get image URL if present
        image_url = None
        if self.has_image:
            for att in self.original_message.attachments:
                if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    image_url = att.url
                    logger.info(f"Found image attachment: {image_url}")
                    break
        
        # Get the AI commands cog and process the request
        ai_commands = interaction.client.get_cog("AICommands")
        if not ai_commands:
            await interaction.followup.send("AI commands not available", ephemeral=True)
            return
        
        try:            
            logger.info(f"Submitting AI request with model: {model_key}, has_image: {self.has_image}, image_url: {image_url}")
            
            # Process the AI request - the defer(thinking=True) will show the typing indicator
            await ai_commands._process_ai_request(
                prompt=self.additional_text,
                model_key=model_key,
                interaction=interaction,
                reference_message=self.reference_message,
                image_url=image_url,
                reply_msg=self.original_message
            )
            
            #Remove the model selection view
            try:
                await interaction.delete_original_response()
            except discord.HTTPException as e:
                logger.warning(f"Could not delete original response: {e}")
            
        except Exception as e:
            logger.exception(f"Error processing AI request: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


@app_commands.context_menu(name="AI Reply")
async def ai_context_menu(interaction: Interaction, message: discord.Message):
    """Unified context menu for AI replies with model selection"""
    if message.author == interaction.client.user:
        content = message.embeds[0].description.strip() if message.embeds and message.embeds[0].description else ""
    else:
        content = message.content
    
    # Get image URLs from original message if it has images
    has_images = False
    for att in message.attachments:
        if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            has_images = True
            break
    
    # Format reference message
    reference_message = f"Message from {message.author.name}: {content}"
    if has_images:
        reference_message += " [This message contains an image attachment]"
    
    modal = AIContextMenus.ModelSelectModal(reference_message, message, interaction.channel)
    await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(AICommands(bot))
    await bot.add_cog(AIContextMenus(bot))
    
    # Register the unified context menu command
    bot.tree.add_command(ai_context_menu)