import time
import logging
import discord
from discord.ext import commands

from generic_fun import perform_fun_query  # import our shared function

logger = logging.getLogger(__name__)

class FunCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="fun")
    async def fun(self, ctx: commands.Context, *, prompt: str):
        """
        Fun mode reply command.
        Usage: !fun <your message>
        """
        start_time = time.time()
        # Retrieve the API utility cog
        api_cog = self.bot.get_cog("APIUtils")
        if not api_cog:
            return await ctx.reply("API utility cog not loaded!")
        
        try:
            result, elapsed = await perform_fun_query(prompt, api_cog, ctx.channel)
        except Exception as e:
            error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            return await ctx.reply(embed=error_embed)
        
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"Deepseek V3 (Fun Mode) | generated in {elapsed} seconds")
        # Instead of sending a new message, we reply to the command invocation.
        await ctx.reply(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCommands(bot))