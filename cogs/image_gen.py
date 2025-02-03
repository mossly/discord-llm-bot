import time
import discord
import openai
from discord.ext import commands
from message_utils import delete_msg
from embed_utils import send_embed
from status_utils import update_status

class ImageGen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def generate_image(self, img_prompt, img_quality, img_size):
        print("Entering generate_image function (COG)")
        response = openai.images.generate(
            model="dall-e-3",
            prompt=img_prompt,
            size=img_size,
            quality=img_quality,
            n=1,
        )
        # Grab the image URLs from the response (assumes response.data is an iterable with .url)
        image_urls = [data.url for data in response.data]
        print("Generated image URL:", image_urls)
        return image_urls

    @commands.command(name="gen")
    async def gen(self, ctx, *, prompt):
        start_time = time.time()
        # Default settings
        quality = "standard"
        size = "1024x1024"
        footer_text_parts = ["DALL·E 3"]

        # Parse flags from the prompt text.
        args = prompt.split()
        prompt_without_flags = []
        for arg in args:
            if arg == "-hd":
                quality = "hd"
                footer_text_parts.append("HD")
            elif arg == "-l":
                size = "1792x1024"
                footer_text_parts.append("Landscape")
            elif arg == "-p":
                size = "1024x1792"
                footer_text_parts.append("Portrait")
            else:
                prompt_without_flags.append(arg)
        prompt_final = " ".join(prompt_without_flags)
        
        # Update status in the channel.
        status_msg = await update_status(None, "...generating image...", channel=ctx.channel)
        try:
            result_urls = await self.generate_image(prompt_final, quality, size)
        except Exception as e:
            await delete_msg(status_msg)
            await ctx.send(f"Error generating image: {e}")
            return

        generation_time = round(time.time() - start_time, 2)
        footer_text_parts.append(f"generated in {generation_time} seconds")
        footer_text = " | ".join(footer_text_parts)
        await delete_msg(status_msg)
        
        # Send an embed for each image URL received.
        for url in result_urls:
            embed = discord.Embed(title="", description=prompt_final, color=0x32a956)
            embed.set_image(url=url)
            embed.set_footer(text=footer_text)
            await send_embed(ctx.channel, embed)

# Cog setup
async def setup(bot):
    await bot.add_cog(ImageGen(bot))