import os
import asyncio
import logging
from discord.ext import commands

logger = logging.getLogger(__name__)

class FunPrompt(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load fun prompt from environment variable or use default.
        self.fun_prompt = os.getenv("FUN_PROMPT", "Let's have some fun!")

    def _save_fun_prompt(self) -> str:
        """
        Synchronously writes the fun prompt to /data/fun.txt.
        Returns the full file path.
        """
        data_folder = "/data"
        # Ensure the /data directory exists.
        if not os.path.exists(data_folder):
            os.makedirs(data_folder, exist_ok=True)
        file_path = os.path.join(data_folder, "fun.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.fun_prompt)
        logger.info("Fun prompt saved to %s", file_path)
        return file_path

    @commands.command(name="savefunprompt")
    @commands.is_owner()
    async def save_fun_prompt(self, ctx: commands.Context) -> None:
        """
        Owner-only command that saves the fun prompt to /data/fun.txt.
        Usage: !savefunprompt
        """
        try:
            # Run the blocking file I/O in a separate thread.
            file_path = await asyncio.to_thread(self._save_fun_prompt)
            await ctx.send(f"Fun prompt saved to {file_path}")
        except Exception as e:
            logger.exception("Failed to save fun prompt: %s", e)
            await ctx.send("Failed to save fun prompt.")

async def setup(bot: commands.Bot):
    await bot.add_cog(FunPrompt(bot))