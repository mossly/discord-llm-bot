import logging
import discord
from discord import app_commands, Interaction, Embed, Attachment
from discord.ext import commands
from generic_chat import prepare_chat_parameters, perform_chat_query

logger = logging.getLogger(__name__)

class ChatSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="chat",
        description="Generate a reply using your prompt; optionally attach a text file or image."
    )
    async def chat(self, interaction: Interaction, prompt: str, attachment: Attachment = None) -> None:
        await interaction.response.defer()
        attachments = [attachment] if attachment else []
        final_prompt, image_url, model, reply_mode, reply_footer, _ = await prepare_chat_parameters(prompt, attachments, ctx=interaction, is_slash=True)
        duck_cog = self.bot.get_cog("DuckDuckGo")
        try:
            result, elapsed, final_footer = await perform_chat_query(
                prompt=final_prompt,
                api_cog=self.bot.get_cog("APIUtils"),
                channel=interaction.channel,
                duck_cog=duck_cog,
                image_url=image_url,
                reference_message="",
                model=model,
                reply_mode=reply_mode,
                reply_footer=reply_footer
            )
        except Exception as e:
            logger.exception("Error in slash chat command: %s", e)
            return await interaction.followup.send(f"Error generating reply: {e}")
        embed = Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{final_footer} | generated in {elapsed} seconds")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChatSlash(bot))