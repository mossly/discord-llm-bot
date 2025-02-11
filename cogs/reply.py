import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class ReplyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only process messages from human users that reply to another message.
        if message.author.bot:
            return
        if not message.reference:
            return

        # If the message already starts with a command prefix, let it be handled normally.
        if message.content.startswith("!"):
            return

        # Attempt to fetch the referenced message.
        try:
            ref_msg = message.reference.cached_message
            if ref_msg is None:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
        except Exception as e:
            logger.exception("Failed to fetch referenced message: %s", e)
            return

        # Only continue if the referenced message is from our bot.
        if ref_msg.author != self.bot.user:
            return

        # Determine conversation mode from the referenced message’s embed footer.
        # (Assumes that fun-mode bot replies have a footer that includes "Deepseek" and/or "Fun Mode".)
        mode = "chat"  # default to chat mode
        ref_footer = ""
        if ref_msg.embeds and ref_msg.embeds[0].footer and ref_msg.embeds[0].footer.text:
            ref_footer = ref_msg.embeds[0].footer.text
            if "deepseek" in ref_footer.lower() or "fun" in ref_footer.lower():
                mode = "fun"

        logger.info("Reply detected from %s. Determined mode: %s", message.author, mode)

        # Determine which existing command to invoke.
        command_name = "fun" if mode == "fun" else "chat"

        # Modify the message content so it looks like a command invocation.
        original_content = message.content
        message.content = f"!{command_name} {original_content}"

        # Pass the modified message on to the command processor.
        await self.bot.process_commands(message)

    async def cog_load(self):
        logger.info("ReplyCog loaded.")

    async def cog_unload(self):
        logger.info("ReplyCog unloaded.")

async def setup(bot: commands.Bot):
    await bot.add_cog(ReplyCog(bot))