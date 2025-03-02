import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class ReferenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_reference_message(self, ctx: commands.Context) -> str:
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

async def setup(bot: commands.Bot):
    await bot.add_cog(ReferenceCog(bot))