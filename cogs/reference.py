import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class ReferenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_reference_message(self, ctx: commands.Context) -> str:
        """
        Helper to fetch the referenced message’s content.
        • If the referenced message is from the bot and has an embed,
          returns the embed’s description.
        • Otherwise, returns the plain text of that message.
        """
        if ctx.message.reference:
            try:
                if ctx.message.reference.cached_message:
                    ref_msg = ctx.message.reference.cached_message
                else:
                    ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.author == self.bot.user:
                    if ref_msg.embeds and ref_msg.embeds[0].description:
                        return ref_msg.embeds[0].description.strip()
                    else:
                        return ""
                else:
                    return ref_msg.content
            except Exception as e:
                logger.exception("Error retrieving reference message: %s", e)
                return ""
        return ""

    @commands.command(name="ref")
    async def ref(self, ctx: commands.Context):
        """
        Show the referenced message (if any). This can be used to verify
        that a reply to a prior message is being interpreted correctly.
        """
        reference_text = await self.get_reference_message(ctx)
        if reference_text:
            await ctx.send(f"Referenced message: {reference_text}")
        else:
            await ctx.send("No reference message found or it is empty.")

    async def cog_load(self):
        logger.info("ReferenceCog loaded.")

    async def cog_unload(self):
        logger.info("ReferenceCog unloaded.")

async def setup(bot: commands.Bot):
    await bot.add_cog(ReferenceCog(bot))