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
        "system_prompt": "Use markdown formatting."
    },
    "fun": {
        "name": "Fun Mode",
        "function": "perform_fun_query",
        "color": 0x32a956,
        "default_model": "deepseek/deepseek-chat",
        "default_footer": "Deepseek V3 (Fun Mode)",
        "api_model": "deepseek/deepseek-chat",
        "system_prompt": None
    }
}

class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None, 
                                 attachments=None, reference_message=None, image_url=None):
        """Unified handler for all AI requests regardless of command type"""
        config = MODEL_CONFIG[model_key]
        channel = ctx.channel if ctx else interaction.channel
        api_cog = self.bot.get_cog("APIUtils")
        duck_cog = self.bot.get_cog("DuckDuckGo")
        
        if config["function"] == "perform_chat_query":
            from generic_chat import prepare_chat_parameters, perform_chat_query, extract_suffixes
            
            # Validate image attachments
            if attachments:
                has_image = any(att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) for att in attachments)
                if has_image and not config.get("supports_images", False):
                    error_embed = Embed(
                        title="ERROR",
                        description="Image attachments only supported with GPT-4o-mini",
                        color=0xDC143C
                    )
                    if ctx:
                        await ctx.reply(embed=error_embed)
                    else:
                        await interaction.followup.send(embed=error_embed)
                    return
                
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
                error_embed = Embed(title="ERROR", description="x_x", color=0xDC143C)
                error_embed.set_footer(text=f"Error generating reply: {e}")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)
                    
        elif config["function"] == "perform_fun_query":
            from generic_fun import perform_fun_query
            try:
                # For text commands (using ctx), use status updates
                # For slash commands (using interaction), the "thinking" state is already set
                if ctx:
                    status_msg = await update_status(None, "...generating fun reply...", channel=channel)
                    try:
                        result, elapsed = await perform_fun_query(
                            prompt=prompt,
                            api_cog=api_cog,
                            channel=channel,
                            image_url=image_url,
                            reference_message=reference_message,
                            show_status=False  # Don't show status again in the function
                        )
                    finally:
                        from message_utils import delete_msg
                        await delete_msg(status_msg)
                else:  # Slash command
                    result, elapsed = await perform_fun_query(
                        prompt=prompt,
                        api_cog=api_cog,
                        channel=channel,
                        image_url=image_url,
                        reference_message=reference_message,
                        show_status=False  # Don't show status, Discord's "thinking" state is used
                    )
                final_footer = config["default_footer"]
            except Exception as e:
                logger.exception(f"Error in {model_key} request: %s", e)
                error_embed = Embed(title="ERROR", description="x_x", color=0xDC143C)
                error_embed.set_footer(text=f"Error generating reply: {e}")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)

        # Create and send the response embed
        embed = Embed(title="", description=result, color=config["color"])
        embed.set_footer(text=f"{final_footer} | generated in {elapsed} seconds")
        
        if ctx:  # Text command
            await send_embed(ctx.channel, embed, reply_to=ctx.message)
        else:  # Slash command
            await interaction.followup.send(embed=embed)
            
    # ===== TEXT COMMANDS =====
    
    @commands.command(name="gpt")
    async def gpt_text(self, ctx: commands.Context, *, prompt: str):
        """Chat with GPT - text command"""
        await self._process_ai_request(prompt, "gpt", ctx=ctx, attachments=ctx.message.attachments)

    @commands.command(name="fun")
    async def fun_text(self, ctx: commands.Context, *, prompt: str):
        """Fun mode chat - text command"""
        await self._process_ai_request(prompt, "fun", ctx=ctx, attachments=ctx.message.attachments)
    
    @commands.command(name="deepseek")
    async def deepseek_text(self, ctx: commands.Context, *, prompt: str):
        """Chat with Deepseek - text command"""
        await self._process_ai_request(prompt, "deepseek", ctx=ctx, attachments=ctx.message.attachments)
        
    @commands.command(name="chat")
    async def chat_text(self, ctx: commands.Context, model: Optional[str] = "gpt-o3-mini", *, prompt: str):
        """
        Generic chat command with model selection
        Usage: !chat [model] your message
        Models: gpt, deepseek, fun
        """
        # Normalize model name and validate
        model_key = model.lower()
        if model_key not in MODEL_CONFIG:
            await ctx.reply(f"Unknown model '{model}'. Available models: {', '.join(MODEL_CONFIG.keys())}")
            return
            
        await self._process_ai_request(prompt, model_key, ctx=ctx, attachments=ctx.message.attachments)
        
    # ===== SLASH COMMANDS =====
    
    @app_commands.command(name="gpt", description="Chat with GPT - provide a prompt and optionally attach content")
    async def gpt_slash(self, interaction: Interaction, prompt: str, attachment: Optional[Attachment] = None):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, "gpt", interaction=interaction, attachments=attachments)

    @app_commands.command(name="fun", description="Fun mode chat - provide a prompt and optionally attach content")
    async def fun_slash(self, interaction: Interaction, prompt: str, attachment: Optional[Attachment] = None):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, "fun", interaction=interaction, attachments=attachments)
    
    @app_commands.command(name="deepseek", description="Chat with Deepseek - provide a prompt and optionally attach content")
    async def deepseek_slash(self, interaction: Interaction, prompt: str, attachment: Optional[Attachment] = None):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, "deepseek", interaction=interaction, attachments=attachments)

    @app_commands.command(name="chat", description="Generic AI chat with model selection")
    @app_commands.describe(
        model="The AI model to use for the response",
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
        
    # Context menu base modal class
    class AIReplyModal(discord.ui.Modal):
        additional_input = discord.ui.TextInput(
            label="Additional Input (Optional)",
            style=discord.TextStyle.long,
            required=False,
            placeholder="Add any extra context or instructions..."
        )
        
        def __init__(self, model_key, reference_message, channel):
            self.model_key = model_key
            self.reference_message = reference_message
            self.channel = channel
            self.config = MODEL_CONFIG[model_key]
            super().__init__(title=f"{self.config['name']} Reply")
            
        async def on_submit(self, interaction: Interaction):
            await interaction.response.defer(thinking=True)
            additional_text = self.additional_input.value or ""

            ai_commands = interaction.client.get_cog("AICommands")
            if not ai_commands:
                await interaction.followup.send("AI commands not available", ephemeral=True)
                return
                
            await ai_commands._process_ai_request(
                prompt=additional_text,
                model_key=self.model_key,
                interaction=interaction,
                reference_message=self.reference_message
            )

    # Generic Reply modal with model selection
    class ModelSelectModal(discord.ui.Modal, title="AI Reply"):
        additional_input = discord.ui.TextInput(
            label="Additional Input (Optional)",
            style=discord.TextStyle.long,
            required=False,
            placeholder="Add any extra context or instructions..."
        )
        
        def __init__(self, reference_message, channel):
            super().__init__()
            self.reference_message = reference_message
            self.channel = channel
            self.add_model_select()
            
        def add_model_select(self):
            # Create a select menu for model selection
            self.model_select = discord.ui.Select(
                placeholder="Choose AI model",
                options=[
                    discord.SelectOption(label="GPT", value="gpt", description="OpenAI GPT model"),
                    discord.SelectOption(label="Deepseek", value="deepseek", description="Deepseek standard model"),
                    discord.SelectOption(label="Fun Mode", value="fun", description="Deepseek with fun personality")
                ]
            )
            # Create placeholder item since Modal can't have selects directly
            # (This is a workaround - in practice, you'd need to use a View)

        async def on_submit(self, interaction: Interaction):
            await interaction.response.defer(thinking=True)
            additional_text = self.additional_input.value or ""
            
            # This is a workaround since Modal can't have Select components
            # In a real implementation, you'd need to show a follow-up view with the Select
            # For this example, we'll default to GPT
            model_key = "gpt"

            ai_commands = interaction.client.get_cog("AICommands")
            if not ai_commands:
                await interaction.followup.send("AI commands not available", ephemeral=True)
                return
                
            await ai_commands._process_ai_request(
                prompt=additional_text,
                model_key=model_key,
                interaction=interaction,
                reference_message=self.reference_message
            )

# ===== CONTEXT MENU COMMANDS =====

@app_commands.context_menu(name="GPT Reply")
async def gpt_context_menu(interaction: Interaction, message: discord.Message):
    """Context menu for GPT replies"""
    if message.author == interaction.client.user:
        content = message.embeds[0].description.strip() if message.embeds and message.embeds[0].description else ""
    else:
        content = message.content
        
    reference_message = f"Message from {message.author.name}: {content}"
    modal = AIContextMenus.AIReplyModal("gpt", reference_message, interaction.channel) 
    await interaction.response.send_modal(modal)

@app_commands.context_menu(name="Deepseek Reply")
async def deepseek_context_menu(interaction: Interaction, message: discord.Message):
    """Context menu for Deepseek replies"""
    if message.author == interaction.client.user:
        content = message.embeds[0].description.strip() if message.embeds and message.embeds[0].description else ""
    else:
        content = message.content
        
    reference_message = f"Message from {message.author.name}: {content}"
    modal = AIContextMenus.AIReplyModal("deepseek", reference_message, interaction.channel)
    await interaction.response.send_modal(modal)

@app_commands.context_menu(name="Fun Mode Reply")
async def fun_context_menu(interaction: Interaction, message: discord.Message):
    """Context menu for Fun Mode replies"""
    if message.author == interaction.client.user:
        content = message.embeds[0].description.strip() if message.embeds and message.embeds[0].description else ""
    else:
        content = message.content
        
    reference_message = f"Message from {message.author.name}: {content}"
    modal = AIContextMenus.AIReplyModal("fun", reference_message, interaction.channel)
    await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(AICommands(bot))
    await bot.add_cog(AIContextMenus(bot))
    
    # Register context menu commands
    bot.tree.add_command(gpt_context_menu)
    bot.tree.add_command(deepseek_context_menu)
    bot.tree.add_command(fun_context_menu)