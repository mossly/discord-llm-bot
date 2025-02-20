import time
import logging
import discord
from discord import app_commands, Interaction, Embed
from discord.ext import commands

from generic_chat import extract_suffixes, perform_chat_query

logger = logging.getLogger(__name__)

class ChatReplyModal(discord.ui.Modal, title="Chat Reply"):
    additional_input = discord.ui.TextInput(
        label="Additional Input (Optional)",
        style=discord.TextStyle.long,
        required=False,
        placeholder="Add any extra context or instructions..."
    )

    def __init__(self, *, reference_message: str, api_cog, channel: discord.TextChannel):
        super().__init__()
        self.reference_message = reference_message
        self.api_cog = api_cog
        self.channel = channel
        self.start_time = time.time()

    async def on_submit(self, interaction: Interaction):
        # Defer the response so Discord shows that we're processing the request.
        await interaction.response.defer()
        additional_text = self.additional_input.value or ""
        # Use our generic suffix extractor. (If no suffix is found, defaults will be returned.)
        cleaned_prompt, model, reply_mode, reply_footer = extract_suffixes(additional_text)
        duck_cog = interaction.client.get_cog("DuckDuckGo")
        try:
            # Call the generic chat function with the additional prompt and the referenced message.
            result, elapsed, final_footer = await perform_chat_query(
                prompt=cleaned_prompt,
                api_cog=self.api_cog,
                channel=self.channel,
                duck_cog=duck_cog,
                image_url=None,
                reference_message=self.reference_message,
                model=model,
                reply_mode=reply_mode,
                reply_footer=reply_footer,
            )
        except Exception as e:
            logger.exception("Error in context chat modal: %s", e)
            await interaction.followup.send(f"Error generating reply: {e}")
            return

        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{final_footer} | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)


@app_commands.context_menu(name="Chat Reply")
async def context_chat_trigger(interaction: Interaction, message: discord.Message):
    """
    When a user right‑clicks a message and selects “Chat Reply,”
    this command extracts text from the target message (if the message is from the bot, use its embed description)
    and then presents a modal so the user can optionally add extra input before generating a reply.
    """
    # Extract context text from the target message.
    if message.author == interaction.client.user:
        if message.embeds and message.embeds[0].description:
            content = message.embeds[0].description.strip()
        else:
            content = ""
    else:
        content = message.content

    reference_message = f"Message from {message.author.name}: {content}"
    api_cog = interaction.client.get_cog("APIUtils")
    if not api_cog:
        await interaction.response.send_message("API utility cog not loaded!", ephemeral=True)
        return

    modal = ChatReplyModal(reference_message=reference_message, api_cog=api_cog, channel=interaction.channel)
    await interaction.response.send_modal(modal)


class ContextChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ContextChat(bot))
    # Register the context menu command with the bot’s application command tree.
    bot.tree.add_command(context_chat_trigger)