import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from embed_utils import send_embed

logger = logging.getLogger(__name__)

# Model configuration - centralized and easy to extend
MODEL_CONFIG = {
    "gpt": {
        "name": "GPT",
        "function": "perform_chat_query",
        "color": 0x32a956,
        "default_model": "o3-mini",
        "default_footer": "o3-mini | default"
    },
    "fun": {
        "name": "Fun Mode",
        "function": "perform_fun_query",
        "color": 0x32a956,
        "default_model": "deepseek/deepseek-chat",
        "default_footer": "Deepseek V3 (Fun Mode)"
    },
}

class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None, 
                                 attachments=None, reference_message=None, image_url=None):
        """Unified handler for all AI requests regardless of command type"""
        config = MODEL_CONFIG[model_key]
        
        # Import the appropriate processing function
        if config["function"] == "perform_chat_query":
            from generic_chat import prepare_chat_parameters, perform_chat_query
            final_prompt, img_url, model, reply_mode, reply_footer, ref_msg = await prepare_chat_parameters(
                prompt, attachments, ctx or interaction, is_slash=bool(interaction)
            )
            if image_url:  # Override with explicitly provided image URL if available
                img_url = image_url
                
            # Use reference_message if explicitly provided
            if reference_message:
                ref_msg = reference_message
                
            duck_cog = self.bot.get_cog("DuckDuckGo")
            api_cog = self.bot.get_cog("APIUtils")
            
            try:
                result, elapsed, final_footer = await perform_chat_query(
                    prompt=final_prompt,
                    api_cog=api_cog,
                    channel=ctx.channel if ctx else interaction.channel,
                    duck_cog=duck_cog,
                    image_url=img_url,
                    reference_message=ref_msg,
                    model=model,
                    reply_mode=reply_mode,
                    reply_footer=reply_footer
                )
            except Exception as e:
                error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                error_embed.set_footer(text=f"Error generating reply: {e}")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)
                    
        elif config["function"] == "perform_fun_query":
            from generic_fun import perform_fun_query
            api_cog = self.bot.get_cog("APIUtils")
            try:
                result, elapsed = await perform_fun_query(
                    prompt=prompt,
                    api_cog=api_cog,
                    channel=ctx.channel if ctx else interaction.channel,
                    image_url=image_url,
                    reference_message=reference_message
                )
                final_footer = config["default_footer"]
            except Exception as e:
                error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                error_embed.set_footer(text=f"Error generating reply: {e}")
                if ctx:
                    return await ctx.reply(embed=error_embed)
                else:
                    return await interaction.followup.send(embed=error_embed)

        # Create and send the response embed
        embed = discord.Embed(title="", description=result, color=config["color"])
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
        
    # ===== SLASH COMMANDS =====
    
    @app_commands.command(name="gpt", description="Chat with GPT - provide a prompt and optionally attach content")
    async def gpt_slash(self, interaction: Interaction, prompt: str, attachment: Attachment = None):
        await interaction.response.defer()
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, "gpt", interaction=interaction, attachments=attachments)

    @app_commands.command(name="fun", description="Fun mode chat - provide a prompt and optionally attach content")
    async def fun_slash(self, interaction: Interaction, prompt: str, attachment: Attachment = None):
        await interaction.response.defer()
        attachments = [attachment] if attachment else []
        await self._process_ai_request(prompt, "fun", interaction=interaction, attachments=attachments)

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
            await interaction.response.defer()
            additional_text = self.additional_input.value or ""

            # Get the appropriate cog and commands handler
            ai_commands = interaction.client.get_cog("AICommands")
            if not ai_commands:
                await interaction.followup.send("AI commands not available", ephemeral=True)
                return
                
            # Process the request through the unified handler
            await ai_commands._process_ai_request(
                prompt=additional_text,
                model_key=self.model_key,
                interaction=interaction,
                reference_message=self.reference_message
            )

# ===== CONTEXT MENU COMMANDS =====

@app_commands.context_menu(name="GPT Reply")
async def gpt_context_menu(interaction: Interaction, message: discord.Message):
    """Context menu for GPT replies"""
    if message.author == interaction.client.user:
        if message.embeds and message.embeds[0].description:
            content = message.embeds[0].description.strip()
        else:
            content = ""
    else:
        content = message.content
        
    reference_message = f"Message from {message.author.name}: {content}"
    
    # Create and show the modal
    modal = AIContextMenus.AIReplyModal("gpt", reference_message, interaction.channel)
    await interaction.response.send_modal(modal)

@app_commands.context_menu(name="Fun Mode Reply")
async def fun_context_menu(interaction: Interaction, message: discord.Message):
    """Context menu for Fun Mode replies"""
    if message.author == interaction.client.user:
        if message.embeds and message.embeds[0].description:
            content = message.embeds[0].description.strip()
        else:
            content = ""
    else:
        content = message.content
        
    reference_message = f"Message from {message.author.name}: {content}"
    
    # Create and show the modal
    modal = AIContextMenus.AIReplyModal("fun", reference_message, interaction.channel)
    await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(AICommands(bot))
    await bot.add_cog(AIContextMenus(bot))
    
    # Register context menu commands
    bot.tree.add_command(gpt_context_menu)
    bot.tree.add_command(fun_context_menu)