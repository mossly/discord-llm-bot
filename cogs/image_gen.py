import time
import asyncio
import discord
import openai
import logging
from discord.ext import commands
from discord import app_commands
from typing import Literal
import aiohttp
import io

from message_utils import delete_msg
from embed_utils import send_embed

logger = logging.getLogger(__name__)

class ImageGen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def generate_image(self, img_prompt: str, img_quality: str, img_size: str):
        logger.info("Entering generate_image function (COG) with prompt: '%s', quality: '%s', size: '%s'",
                    img_prompt, img_quality, img_size)
        loop = asyncio.get_running_loop()
        # Offload the blocking call to the default executor
        response = await loop.run_in_executor(
            None,
            lambda: openai.images.generate(
                model="dall-e-3",
                prompt=img_prompt,
                size=img_size,
                quality=img_quality,
                n=1,
            )
        )
        image_urls = [data.url for data in response.data]
        logger.info("Generated image URL(s): %s", image_urls)
        return image_urls

    @app_commands.command(name="gen", description="Generate an image using DALL·E 3")
    @app_commands.describe(
        prompt="The prompt for the image",
        hd="Return image in HD quality",
        orientation="Choose the image orientation (Square, Landscape, or Portrait)"
    )
    async def gen(
        self,
        interaction: discord.Interaction,
        prompt: str,
        hd: bool = False,
        orientation: Literal["Square", "Landscape", "Portrait"] = "Square"
    ):
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

        # Download each image and send it as an attachment to ensure it displays in the embed.
        for idx, url in enumerate(result_urls):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.error("Failed to fetch image from URL: %s", url)
                            await interaction.followup.send("Failed to retrieve image!")
                            continue
                        image_data = await resp.read()
            except Exception as e:
                logger.exception("Error downloading image from URL: %s", url)
                await interaction.followup.send(f"Error downloading image: {e}")
                continue

            file = discord.File(io.BytesIO(image_data), filename=f"generated_image_{idx}.png")
            embed = discord.Embed(title="", description=prompt, color=0x32a956)
            # Use the 'attachment://' URL to reference the file attached below.
            embed.set_image(url=f"attachment://generated_image_{idx}.png")
            embed.set_footer(text=footer_text)
            await interaction.followup.send(file=file, embed=embed)
            logger.info("Sent generated image embed for URL: %s", url)

        logger.info("Image generation command completed in %s seconds", generation_time)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageGen(bot))