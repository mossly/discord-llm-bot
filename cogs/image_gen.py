import time
import asyncio
import discord
import openai
import logging
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional
import aiohttp
import io
import os
import base64
from user_quotas import quota_manager

logger = logging.getLogger(__name__)

class ImageGen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.openrouter_client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        
    def calculate_image_cost(self, model: str, size: str, quality: str = "standard", is_edit: bool = False) -> float:
        """Calculate the cost of image generation based on model and parameters"""
        if model == "dall-e-3":
            if quality == "hd":
                return 0.08  # HD quality
            else:
                return 0.04  # Standard quality
        elif model == "gpt-image-1":
            # GPT-image-1 pricing is more complex, base cost for now
            # This might need adjustment based on actual token usage
            if is_edit:
                return 0.08  # Edit operations tend to be more expensive
            else:
                return 0.06  # Generation with GPT-image-1
        elif model == "dall-e-2":
            if size == "1024x1024":
                return 0.02
            elif size == "512x512":
                return 0.018
            elif size == "256x256":
                return 0.016
        return 0.04  # Default fallback
        
    def extract_usage_info(self, response) -> dict:
        """Extract usage/cost information from API response"""
        usage_info = {}
        
        # Check for usage in main response
        if hasattr(response, 'usage'):
            usage = response.usage
            logger.info(f"Found usage info: {usage}")
            
            # Extract common usage fields
            if hasattr(usage, 'total_tokens'):
                usage_info['total_tokens'] = usage.total_tokens
            if hasattr(usage, 'prompt_tokens'):
                usage_info['prompt_tokens'] = usage.prompt_tokens
            if hasattr(usage, 'completion_tokens'):
                usage_info['completion_tokens'] = usage.completion_tokens
            if hasattr(usage, 'total_cost'):
                usage_info['total_cost'] = usage.total_cost
                
        # Check for usage in data items
        if hasattr(response, 'data') and response.data:
            for data in response.data:
                if hasattr(data, 'usage'):
                    usage_info.update(vars(data.usage))
                    
        return usage_info

    async def generate_image(self, img_prompt: str, img_quality: str, img_size: str, model: str = "dall-e-3", image_input: str = None, is_edit: bool = False):
        logger.info("Entering generate_image function (COG) with prompt: '%s', quality: '%s', size: '%s', model: '%s', is_edit: %s",
                    img_prompt, img_quality, img_size, model, is_edit)
        
        loop = asyncio.get_running_loop()
        
        # Always use OpenAI API for both DALL-E and GPT-image-1
        client = self.openai_client
        api_model = model
        
        if image_input and is_edit and model == "gpt-image-1":
            # Image editing with GPT-image-1
            response = await loop.run_in_executor(
                None,
                lambda: client.images.edit(
                    model=api_model,
                    image=image_input,
                    prompt=img_prompt,
                    size=img_size,
                    n=1,
                )
            )
        else:
            # Image generation (with or without image input for GPT-image-1)
            if model == "gpt-image-1":
                # GPT-image-1 generation
                if image_input:
                    # Use image as input reference
                    response = await loop.run_in_executor(
                        None,
                        lambda: client.images.generate(
                            model=api_model,
                            prompt=img_prompt,
                            size=img_size,
                            n=1,
                        )
                    )
                else:
                    response = await loop.run_in_executor(
                        None,
                        lambda: client.images.generate(
                            model=api_model,
                            prompt=img_prompt,
                            size=img_size,
                            n=1,
                        )
                    )
            else:
                # DALL-E models
                response = await loop.run_in_executor(
                    None,
                    lambda: client.images.generate(
                        model=api_model,
                        prompt=img_prompt,
                        size=img_size,
                        quality=img_quality,
                        n=1,
                    )
                )
        
        # Debug response structure and look for cost/usage info
        logger.info(f"Full response object: {response}")
        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response attributes: {dir(response)}")
        
        # Check for usage information
        if hasattr(response, 'usage'):
            logger.info(f"USAGE INFO FOUND: {response.usage}")
            logger.info(f"Usage type: {type(response.usage)}")
            logger.info(f"Usage attributes: {dir(response.usage)}")
        else:
            logger.info("No 'usage' attribute found in response")
            
        # Look for any cost-related attributes
        cost_attrs = [attr for attr in dir(response) if 'cost' in attr.lower() or 'price' in attr.lower() or 'usage' in attr.lower() or 'token' in attr.lower()]
        logger.info(f"Cost/usage related attributes: {cost_attrs}")
        
        if hasattr(response, 'data'):
            logger.info(f"Response data: {response.data}")
            logger.info(f"Data type: {type(response.data)}")
            if response.data:
                for i, data in enumerate(response.data):
                    logger.info(f"Data item {i}: {data}")
                    logger.info(f"Data item {i} type: {type(data)}")
                    logger.info(f"Data item {i} attributes: {dir(data)}")
                    
                    # Check data items for usage info
                    if hasattr(data, 'usage'):
                        logger.info(f"Data item {i} usage: {data.usage}")

        # Handle different response formats
        image_urls = []
        if hasattr(response, 'data') and response.data:
            for data in response.data:
                if hasattr(data, 'url') and data.url:
                    image_urls.append(data.url)
                elif hasattr(data, 'b64_json') and data.b64_json:
                    # GPT-image-1 might return base64 instead of URL
                    image_urls.append(f"data:image/png;base64,{data.b64_json}")
                else:
                    logger.warning(f"Unexpected data format in response: {data}")
        
        logger.info("Generated image URL(s): %s", image_urls)
        if not image_urls:
            logger.error(f"No valid image URLs found in response: {response}")
            raise Exception("No image URLs returned from API")
            
        # Extract usage information
        usage_info = self.extract_usage_info(response)
        logger.info(f"Extracted usage info: {usage_info}")
        
        return image_urls, usage_info

    @app_commands.command(name="gen", description="Generate or edit an image using DALL·E 3 or GPT-image-1")
    @app_commands.describe(
        prompt="The prompt for the image",
        model="Choose the image generation model",
        hd="Return image in HD quality (DALL-E 3 only)",
        orientation="Choose the image orientation (Square, Landscape, or Portrait)",
        attachment="Optional input image",
        image_mode="How to use the attached image (only for GPT-image-1)"
    )
    async def gen(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: Literal["dall-e-3", "gpt-image-1"] = "dall-e-3",
        hd: bool = False,
        orientation: Literal["Square", "Landscape", "Portrait"] = "Square",
        attachment: Optional[discord.Attachment] = None,
        image_mode: Literal["input", "edit"] = "input"
    ):
        await interaction.response.defer()
        start_time = time.time()
        
        user_id = str(interaction.user.id)
        
        # Check user quota before generating image
        remaining_quota = quota_manager.get_remaining_quota(user_id)
        if remaining_quota == 0:
            await interaction.followup.send("❌ **Quota Exceeded**: You've reached your monthly usage limit. Your quota resets at the beginning of each month.")
            return
        elif remaining_quota != float('inf') and remaining_quota < 0.05:  # Less than 5 cents remaining
            await interaction.followup.send(f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Image generation typically costs $0.04-$0.08.")
            return

        quality = "hd" if hd and model == "dall-e-3" else "standard"
        if orientation == "Landscape":
            size = "1792x1024"
        elif orientation == "Portrait":
            size = "1024x1792"
        else:
            size = "1024x1024"

        footer_text_parts = ["GPT-image-1" if model == "gpt-image-1" else "DALL·E 3"]
        if hd and model == "dall-e-3":
            footer_text_parts.append("HD")
        if orientation in ("Landscape", "Portrait"):
            footer_text_parts.append(orientation)
            
        image_input = None
        is_edit = False
        if attachment:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                if model != "gpt-image-1":
                    await interaction.followup.send("Image attachments are only supported with GPT-image-1 model.")
                    return
                try:
                    image_bytes = await attachment.read()
                    image_input = io.BytesIO(image_bytes)
                    is_edit = (image_mode == "edit")
                    mode_text = "Edit" if is_edit else "Input"
                    footer_text_parts.append(mode_text)
                except Exception as e:
                    logger.error(f"Error reading attachment: {e}")
                    await interaction.followup.send("Error reading image attachment. Please try again.")
                    return
            else:
                await interaction.followup.send("Please attach a valid image file (PNG, JPG, JPEG, or WebP).")
                return

        try:
            result_urls, usage_info = await self.generate_image(prompt, quality, size, model, image_input, is_edit)
        except Exception as e:
            logger.exception("Error generating image for prompt: '%s'", prompt)
            await interaction.followup.send(f"Error generating image: {e}")
            return

        generation_time = round(time.time() - start_time, 2)
        
        # Use actual cost from API if available, otherwise calculate estimate
        if usage_info and 'total_cost' in usage_info:
            cost = usage_info['total_cost']
            cost_source = "actual"
        else:
            cost = self.calculate_image_cost(model, size, quality, is_edit)
            cost_source = "estimated"
        
        # Track usage in user quota system
        if cost > 0:
            if quota_manager.add_usage(user_id, cost):
                logger.info(f"Tracked ${cost:.4f} image generation usage for user {user_id}")
            else:
                logger.warning(f"Failed to track image generation usage for user {user_id}")
        
        # Create footer with cost and timing
        footer_first_line = " | ".join(footer_text_parts)
        cost_text = f"${cost:.4f}" if cost_source == "actual" else f"~${cost:.2f}"
        footer_second_line = f"{cost_text} | {generation_time} seconds"
        footer_text = f"{footer_first_line}\n{footer_second_line}"

        for idx, url in enumerate(result_urls):
            try:
                if url.startswith("data:image/"):
                    # Handle base64 data URLs
                    base64_data = url.split(",", 1)[1]
                    image_data = base64.b64decode(base64_data)
                else:
                    # Handle regular URLs
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                logger.error("Failed to fetch image from URL: %s", url)
                                await interaction.followup.send("Failed to retrieve image!")
                                continue
                            image_data = await resp.read()
            except Exception as e:
                logger.exception("Error processing image from URL: %s", url)
                await interaction.followup.send(f"Error processing image: {e}")
                continue

            file = discord.File(io.BytesIO(image_data), filename=f"generated_image_{idx}.png")
            embed = discord.Embed(title="", description=prompt, color=0x32a956)
            embed.set_image(url=f"attachment://generated_image_{idx}.png")
            embed.set_footer(text=footer_text)
            await interaction.followup.send(file=file, embed=embed)
            logger.info("Sent generated image embed for URL: %s", url[:50] + "..." if len(url) > 50 else url)

        logger.info("Image generation command completed in %s seconds", generation_time)

    async def extract_image_from_message(self, message: discord.Message) -> Optional[io.BytesIO]:
        """Extract image from a message (attachment or embed)"""
        # Check attachments first
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                try:
                    image_bytes = await attachment.read()
                    return io.BytesIO(image_bytes)
                except Exception as e:
                    logger.error(f"Error reading attachment: {e}")
                    
        # Check embeds for images
        for embed in message.embeds:
            if embed.image:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(embed.image.url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                return io.BytesIO(image_bytes)
                except Exception as e:
                    logger.error(f"Error downloading embed image: {e}")
                    
        return None


class ImageEditModal(discord.ui.Modal, title='Generate with Image'):
    def __init__(self, image_cog: ImageGen, original_message: discord.Message):
        super().__init__()
        self.image_cog = image_cog
        self.original_message = original_message

    prompt = discord.ui.TextInput(
        label='Prompt',
        placeholder='Describe what you want to generate or how to edit this image...',
        required=True,
        max_length=1000
    )
    
    model = discord.ui.TextInput(
        label='Model (gpt-image-1)',
        placeholder='gpt-image-1',
        default='gpt-image-1',
        required=False,
        max_length=20
    )
    
    image_mode = discord.ui.TextInput(
        label='Image Mode (input/edit)',
        placeholder='input',
        default='input',
        required=False,
        max_length=10
    )
    
    orientation = discord.ui.TextInput(
        label='Orientation (Square/Landscape/Portrait)',
        placeholder='Square',
        default='Square',
        required=False,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        
        # Check user quota before generating image
        remaining_quota = quota_manager.get_remaining_quota(user_id)
        if remaining_quota == 0:
            await interaction.followup.send("❌ **Quota Exceeded**: You've reached your monthly usage limit. Your quota resets at the beginning of each month.")
            return
        elif remaining_quota != float('inf') and remaining_quota < 0.05:  # Less than 5 cents remaining
            await interaction.followup.send(f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Image generation typically costs $0.04-$0.08.")
            return
        
        # Extract image from original message
        image_input = await self.image_cog.extract_image_from_message(self.original_message)
        if not image_input:
            await interaction.followup.send("No image found in the original message.")
            return
            
        start_time = time.time()
        model_str = self.model.value.strip() or "gpt-image-1"
        orientation_str = self.orientation.value.strip() or "Square"
        image_mode_str = self.image_mode.value.strip().lower() or "input"
        
        if orientation_str == "Landscape":
            size = "1792x1024"
        elif orientation_str == "Portrait":
            size = "1024x1792"
        else:
            size = "1024x1024"
            
        is_edit = (image_mode_str == "edit")
        mode_text = "Edit" if is_edit else "Input"
        footer_text_parts = ["GPT-image-1", mode_text]
        if orientation_str in ("Landscape", "Portrait"):
            footer_text_parts.append(orientation_str)
            
        try:
            result_urls, usage_info = await self.image_cog.generate_image(self.prompt.value, "standard", size, model_str, image_input, is_edit)
        except Exception as e:
            logger.exception("Error generating image for prompt: '%s'", self.prompt.value)
            await interaction.followup.send(f"Error generating image: {e}")
            return
            
        generation_time = round(time.time() - start_time, 2)
        
        # Use actual cost from API if available, otherwise calculate estimate
        if usage_info and 'total_cost' in usage_info:
            cost = usage_info['total_cost']
            cost_source = "actual"
        else:
            cost = self.image_cog.calculate_image_cost(model_str, size, "standard", is_edit)
            cost_source = "estimated"
        
        # Track usage in user quota system
        if cost > 0:
            if quota_manager.add_usage(user_id, cost):
                logger.info(f"Tracked ${cost:.4f} image generation usage for user {user_id}")
            else:
                logger.warning(f"Failed to track image generation usage for user {user_id}")
        
        # Create footer with cost and timing
        footer_first_line = " | ".join(footer_text_parts)
        cost_text = f"${cost:.4f}" if cost_source == "actual" else f"~${cost:.2f}"
        footer_second_line = f"{cost_text} | {generation_time} seconds"
        footer_text = f"{footer_first_line}\n{footer_second_line}"
        
        for idx, url in enumerate(result_urls):
            try:
                if url.startswith("data:image/"):
                    # Handle base64 data URLs
                    base64_data = url.split(",", 1)[1]
                    image_data = base64.b64decode(base64_data)
                else:
                    # Handle regular URLs
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                logger.error("Failed to fetch image from URL: %s", url)
                                await interaction.followup.send("Failed to retrieve image!")
                                continue
                            image_data = await resp.read()
            except Exception as e:
                logger.exception("Error processing image from URL: %s", url)
                await interaction.followup.send(f"Error processing image: {e}")
                continue
                
            file = discord.File(io.BytesIO(image_data), filename=f"generated_image_{idx}.png")
            embed = discord.Embed(title="", description=self.prompt.value, color=0x32a956)
            embed.set_image(url=f"attachment://generated_image_{idx}.png")
            embed.set_footer(text=footer_text)
            await interaction.followup.send(file=file, embed=embed)
            logger.info("Sent generated image embed for URL: %s", url[:50] + "..." if len(url) > 50 else url)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageGen(bot))