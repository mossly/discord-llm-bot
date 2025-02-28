import time
import discord
import openai
import logging
from discord.ext import commands
from discord import app_commands
from typing import Literal

from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

class ImageGen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def generate_image(self, img_prompt: str, img_quality: str, img_size: str):
        logger.info("Entering generate_image function (COG) with prompt: '%s', quality: '%s', size: '%s'",
                    img_prompt, img_quality, img_size)
        response = openai.images.generate(
            model="dall-e-3",
            prompt=img_prompt,
            size=img_size,
            quality=img_quality,
            n=1,
        )
        image_urls = [data.url for data in response.data]
        logger.info("Generated image URL(s): %s", image_urls)
        return image_urls

    @app_commands.command(name="gen", description="Generate an image using DALL·E 3")
    @app_commands.describe(prompt="The prompt for the image",
                           hd="Check for HD quality",
                           orientation="Choose the image orientation")
    async def gen(self,
                  interaction: discord.Interaction,
                  prompt: str,
                  hd: bool = False,
                  orientation: Literal["Square", "Landscape", "Portrait"] = "Square"):
        await interaction.response.defer()
        start_time = time.time()

        quality = "hd" if hd else "standard"
        if orientation == "Landscape":
            size = "1792x1024"
        elif orientation == "Portrait":
            size = "1024x1792"
        else:
            size = "1024x1024"

        footer_text_parts = ["DALL·E 3"]
        if hd:
            footer_text_parts.append("HD")
        if orientation in ("Landscape", "Portrait"):
            footer_text_parts.append(orientation)

        try:
            result_urls = await self.generate_image(prompt, quality, size)
        except Exception as e:
            logger.exception("Error generating image for prompt: '%s'", prompt)
            await interaction.followup.send(f"Error generating image: {e}")
            return

        generation_time = round(time.time() - start_time, 2)
        footer_text_parts.append(f"generated in {generation_time} seconds")
        footer_text = " | ".join(footer_text_parts)

        for url in result_urls:
            embed = discord.Embed(title="", description=prompt, color=0x32a956)
            embed.set_image(url=url)
            embed.set_footer(text=footer_text)
            await interaction.followup.send(embed=embed)
            logger.info("Sent generated image embed for URL: %s", url)

        logger.info("Image generation command completed in %s seconds", generation_time)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageGen(bot))