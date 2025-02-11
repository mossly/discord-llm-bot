import os
import asyncio
import json
import logging
from discord.ext import commands

logger = logging.getLogger(__name__)

class FunPrompt(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load messages from environment variables or use defaults
        self.fun_prompt = os.getenv("FUN_PROMPT", "Let's have some fun!")
        self.rusk_lore = os.getenv("RUSK_LORE", "Default Rusk lore text")

    def _save_fun_prompt(self) -> str:
        """
        Synchronously writes the fun prompt to /data/fun.txt.
        Returns the full file path.
        """
        data_folder = "/data"
        if not os.path.exists(data_folder):
            os.makedirs(data_folder, exist_ok=True)
        file_path = os.path.join(data_folder, "fun.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.fun_prompt)
        logger.info("Fun prompt saved to %s", file_path)
        return file_path

    def _save_rusk_lore(self) -> str:
        """
        Synchronously writes the RUSK_LORE to /data/rusk_lore.json.
        The lore is saved as a JSON object.
        Returns the full file path.
        """
        data_folder = "/data"
        if not os.path.exists(data_folder):
            os.makedirs(data_folder, exist_ok=True)
        file_path = os.path.join(data_folder, "rusk_lore.json")
        data = {"rusk_lore": self.rusk_lore}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info("RUSK_LORE saved to %s", file_path)
        return file_path

    @commands.command(name="savefunprompt")
    @commands.is_owner()
    async def save_fun_prompt(self, ctx: commands.Context) -> None:
        """
        Owner-only command that saves the fun prompt to /data/fun.txt.
        Usage: !savefunprompt
        """
        try:
            file_path = await asyncio.to_thread(self._save_fun_prompt)
            await ctx.send(f"Fun prompt saved to {file_path}")
        except Exception as e:
            logger.exception("Failed to save fun prompt: %s", e)
            await ctx.send("Failed to save fun prompt.")

    @commands.command(name="saverusklore")
    @commands.is_owner()
    async def save_rusk_lore_command(self, ctx: commands.Context) -> None:
        """
        Owner-only command that saves the RUSK_LORE environment variable to /data/rusk_lore.json.
        Usage: !saverusklore
        """
        try:
            file_path = await asyncio.to_thread(self._save_rusk_lore)
            await ctx.send(f"RUSK_LORE saved to {file_path}")
        except Exception as e:
            logger.exception("Failed to save RUSK_LORE: %s", e)
            await ctx.send("Failed to save RUSK_LORE.")

async def setup(bot: commands.Bot):
    await bot.add_cog(FunPrompt(bot))