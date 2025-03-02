import time
import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from typing import Optional, Literal
from embed_utils import send_embed
from status_utils import update_status

logger = logging.getLogger(__name__)

MODEL_CONFIG = {
    "gpt-4o-mini": {
        "name": "GPT-4o-mini by OpenAI",
        "color": 0x32a956,
        "default_footer": "gpt-4o-mini",
        "api_model": "openai/gpt-4o-mini",
        "supports_images": True,
        "api": "openrouter"
    },
    "gpt-o3-mini": {
        "name": "GPT-o3-mini by OpenAI",
        "color": 0x32a956,
        "default_footer": "o3-mini | CoT",
        "api_model": "openai/o3-mini",
        "supports_images": False,
        "api": "openrouter"
    },
    "deepseek-v3": {
        "name": "DeepSeek v3 by DeepSeek",
        "color": 0x32a956, 
        "default_footer": "Deepseek-v3",
        "api_model": "deepseek/deepseek-chat",
        "supports_images": False,
        "api": "openrouter"
    },
    "claude-3.7-sonnet": {
        "name": "Claude 3.7 Sonnet by Anthropic",
        "color": 0x32a956,
        "default_footer": "Claude 3.7 Sonnet",
        "api_model": "anthropic/claude-3.7-sonnet:beta",
        "supports_images": False,
        "api": "openrouter"
    },
    "claude-3.7-sonnet:thinking": {
        "name": "Claude 3.7 Sonnet (Thinking) by Anthropic",
        "color": 0x32a956,
        "default_footer": "Claude 3.7 Sonnet (Thinking)",
        "api_model": "anthropic/claude-3.7-sonnet:thinking",
        "supports_images": False,
        "api": "openrouter"
    },
    "gemini-2.0-flash-lite": {
        "name": "Gemini 2.0 Flash Lite by Google",
        "color": 0x32a956,
        "default_footer": "Gemini 2.0 Flash Lite",
        "api_model": "google/gemini-2.0-flash-lite-001",
        "supports_images": False,
        "api": "openrouter"
    },
    "grok-2": {
        "name": "Grok 2 by X-AI",
        "color": 0x32a956,
        "default_footer": "Grok 2",
        "api_model": "x-ai/grok-2-1212",
        "supports_images": False,
        "api": "openrouter"
    },
    "mistral-large": {
        "name": "Mistral Large by Mistral AI",
        "color": 0x32a956,
        "default_footer": "Mistral Large",
        "api_model": "mistralai/mistral-large-2411",
        "supports_images": False,
        "api": "openrouter"
    }
}

class AICommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def _process_ai_request(self, prompt, model_key, ctx=None, interaction=None, attachments=None, reference_message=None, image_url=None, reply_msg: Optional[discord.Message] = None, fun: bool = False, web_search: bool = False):
        config = MODEL_CONFIG[model_key]
        channel = ctx.channel if ctx else interaction.channel
        api_cog = self.bot.get_cog("APIUtils")
        duck_cog = self.bot.get_cog("DuckDuckGo")
        
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
            from generic_chat import process_attachments, perform_chat_query
            final_prompt, img_url = await process_attachments(prompt, attachments or [], is_slash=(interaction is not None))
        else:
            final_prompt = prompt
            img_url = image_url

        cleaned_prompt = final_prompt
        model = config["api_model"]
        footer = config["default_footer"]
        api = config.get("api", "openai")
            
        try:
            if ctx:
                status_msg = await update_status(None, "...generating reply...", channel=channel)
                try:
                    result, elapsed, footer_with_stats = await perform_chat_query(
                        prompt=cleaned_prompt,
                        api_cog=api_cog,
                        channel=channel,
                        duck_cog=duck_cog,
                        image_url=img_url,
                        reference_message=reference_message,
                        model=model,
                        reply_footer=footer,
                        show_status=False,
                        api=api,
                        use_fun=fun,
                        web_search=web_search
                    )
                finally:
                    from message_utils import delete_msg
                    await delete_msg(status_msg)
            else:
                result, elapsed, footer_with_stats = await perform_chat_query(
                    prompt=cleaned_prompt,
                    api_cog=api_cog,
                    channel=channel,
                    duck_cog=duck_cog,
                    image_url=img_url,
                    reference_message=reference_message,
                    model=model,
                    reply_footer=footer,
                    show_status=False,
                    api=api,
                    use_fun=fun,
                    web_search=web_search
                )
            
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
        
        if ctx or reply_msg:
            channel = ctx.channel if ctx else reply_msg.channel
            message_to_reply = ctx.message if ctx else reply_msg
            await send_embed(channel, embed, reply_to=message_to_reply)
        else:
            await send_embed(interaction.channel, embed, interaction=interaction)

    @app_commands.command(name="chat", description="Select a model and provide a prompt")
    @app_commands.describe(
        model="Model to use for the response",
        fun="Toggle fun mode",
        web_search="Toggle web search",
        prompt="Your query or instructions",
        attachment="Optional attachment (image or text file)"
    )
    async def chat_slash(
        self, 
        interaction: Interaction, 
        model: Literal["gpt-4o-mini", "gpt-o3-mini", "deepseek-v3",
                        "claude-3.7-sonnet", "claude-3.7-sonnet:thinking",
                        "gemini-2.0-flash-lite", "grok-2", "mistral-large"],
        prompt: str, 
        fun: bool = False,
        web_search: bool = False,
        attachment: Optional[Attachment] = None
    ):
        await interaction.response.defer(thinking=True)
        attachments = [attachment] if attachment else []
        username = interaction.user.name
        formatted_prompt = f"{username}: {prompt}"
        
        has_image = False
        if attachment:
            has_image = attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
        
        if has_image and not MODEL_CONFIG[model].get("supports_images", False):
            await interaction.followup.send(
                f"⚠️ Automatically switched to GPT-4o-mini because you attached an image " 
                f"and {MODEL_CONFIG[model]['name']} doesn't support image processing.",
                ephemeral=True
            )
            model = "gpt-4o-mini"
        
        await self._process_ai_request(formatted_prompt, model, interaction=interaction, attachments=attachments, fun=fun, web_search=web_search)

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
                additional_text=formatted_prompt
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
        self.fun = False
        self.web_search = False
        
        options = []
        
        options.append(discord.SelectOption(
            label="GPT-4o-mini", 
            value="gpt-4o-mini",
            description="OpenAI model with image support",
            default=self.has_image
        ))
        
        if not self.has_image:
            options.extend([
                discord.SelectOption(
                    label="GPT-o3-mini", 
                    value="gpt-o3-mini", 
                    description="OpenAI reasoning model",
                    default=not self.has_image
                ),
                discord.SelectOption(
                    label="Deepseek-v3", 
                    value="deepseek-v3", 
                    description="Deepseek chat model"
                ),
                discord.SelectOption(
                    label="Anthropic Claude 3.7 Sonnet", 
                    value="anthropic/claude-3.7-sonnet", 
                    description="Anthropic chat model"
                ),
                discord.SelectOption(
                    label="Anthropic Claude 3.7 Sonnet (Thinking)", 
                    value="anthropic/claude-3.7-sonnet:thinking", 
                    description="Anthropic reasoning model"
                ),
                discord.SelectOption(
                    label="Google Gemini 2.0 Flash Lite", 
                    value="google/gemini-2.0-flash-lite-001", 
                    description="Google chat model"
                ),
                discord.SelectOption(
                    label="X-AI Grok 2", 
                    value="x-ai/grok-2-1212", 
                    description="X-AI chat model"
                )
            ])
        
        self.model_select = discord.ui.Select(
            placeholder="Choose AI model",
            options=options
        )
        self.model_select.callback = self.on_model_select
        self.add_item(self.model_select)
        
        fun_button = discord.ui.Button(
            label="Fun Mode: OFF", 
            style=discord.ButtonStyle.secondary, 
            custom_id="toggle_fun"
        )
        fun_button.callback = self.toggle_fun
        self.add_item(fun_button)
        
        web_search_button = discord.ui.Button(
            label="Web Search: OFF", 
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
        button = [item for item in self.children if isinstance(item, discord.ui.Button) and item.custom_id=="toggle_fun"][0]
        button.label = f"Fun Mode: {'ON' if self.fun else 'OFF'}"
        await interaction.response.edit_message(view=self)
    
    async def toggle_web_search(self, interaction: discord.Interaction):
        self.web_search = not self.web_search
        button = [item for item in self.children if isinstance(item, discord.ui.Button) and item.custom_id=="toggle_web_search"][0]
        button.label = f"Web Search: {'ON' if self.web_search else 'OFF'}"
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
                web_search=self.web_search
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


async def setup(bot: commands.Bot):
    await bot.add_cog(AICommands(bot))
    await bot.add_cog(AIContextMenus(bot))
    
    bot.tree.add_command(ai_context_menu)