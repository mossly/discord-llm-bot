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
from utils.embed_utils import create_error_embed
import os
import base64
from utils.quota_validator import quota_manager

logger = logging.getLogger(__name__)

class ImageGen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.openrouter_client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        
    def calculate_image_cost(self, model: str, size: str, quality: str = "high", is_edit: bool = False) -> float:
        """Calculate the cost of image generation based on model and parameters"""
        if model == "dall-e-3":
            if quality == "hd":
                return 0.08  # HD quality
            else:
                return 0.04  # Standard quality
        elif model == "gpt-image-1":
            # GPT-image-1 pricing with quality considerations
            base_cost = 0.20 if quality == "high" else 0.06  # High quality costs more
            if is_edit:
                return base_cost * 1.3  # Edit operations tend to be more expensive
            else:
                return base_cost
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
    
    def build_footer(self, model: str, quality: str, size: str, is_edit: bool = False, image_inputs: list = None, cost: float = 0, cost_source: str = "estimated", generation_time: float = 0, usage_info: dict = None) -> str:
        """Build standardized footer for image generation"""
        # First line: Model name with modifiers
        footer_parts = []
        
        # Model name
        if model == "gpt-image-1":
            footer_parts.append("GPT-image-1")
        elif model == "dall-e-3":
            footer_parts.append("DALL·E 3")
        elif model == "dall-e-2":
            footer_parts.append("DALL·E 2")
        else:
            footer_parts.append(model)
        
        # Quality
        if quality in ("high", "hd"):
            footer_parts.append("High Quality")
        elif quality in ("standard", "medium", "low"):
            footer_parts.append("Low Quality")
        
        # Orientation
        if size == "1536x1024" or size == "1792x1024":
            footer_parts.append("Landscape")
        elif size == "1024x1536" or size == "1024x1792":
            footer_parts.append("Portrait")
        elif size == "1024x1024":
            footer_parts.append("Square")
        
        # Mode (if using input images)
        if image_inputs:
            mode_text = "Edit" if is_edit else "Input"
            footer_parts.append(mode_text)
            if len(image_inputs) > 1:
                footer_parts.append(f"{len(image_inputs)} images")
        
        first_line = " | ".join(footer_parts)
        
        # Second line: Usage stats (standardized format)
        usage_parts = []
        
        # Token usage (if available from usage_info) - rare for image generation
        if usage_info:
            if 'prompt_tokens' in usage_info and usage_info['prompt_tokens'] > 0:
                input_tokens = usage_info['prompt_tokens']
                if input_tokens >= 1000:
                    input_str = f"{input_tokens / 1000:.1f}k"
                else:
                    input_str = str(input_tokens)
                usage_parts.append(f"{input_str} input tokens")
            if 'completion_tokens' in usage_info and usage_info['completion_tokens'] > 0:
                output_tokens = usage_info['completion_tokens']
                if output_tokens >= 1000:
                    output_str = f"{output_tokens / 1000:.1f}k"
                else:
                    output_str = str(output_tokens)
                usage_parts.append(f"{output_str} output tokens")
        
        # Cost (show $x.xx, but to first non-zero digit if under $0.01)
        if cost >= 0.01:
            cost_str = f"${cost:.2f}"
        elif cost > 0:
            # Find first non-zero digit
            decimal_places = 2
            while cost < (1 / (10 ** decimal_places)) and decimal_places < 10:
                decimal_places += 1
            cost_str = f"${cost:.{decimal_places}f}"
        else:
            cost_str = "$0.00"
        usage_parts.append(cost_str)
        
        # Time
        if generation_time > 0:
            usage_parts.append(f"{generation_time} seconds")
        
        second_line = " | ".join(usage_parts)
        
        return f"{first_line}\n{second_line}"

    async def generate_image_streaming(self, img_prompt: str, img_quality: str, img_size: str, model: str = "gpt-image-1", image_inputs: list = None, is_edit: bool = False, interaction=None):
        """Generate image with streaming support using Responses API"""
        if model != "gpt-image-1":
            # Fallback to regular generation for non-streaming models
            return await self.generate_image(img_prompt, img_quality, img_size, model, image_inputs, is_edit)
        
        # Handle backwards compatibility
        if isinstance(image_inputs, io.BytesIO):
            image_inputs = [image_inputs]
        elif image_inputs is None:
            image_inputs = []
            
        num_images = len(image_inputs)
        logger.info("Entering streaming generate_image function with prompt: '%s', quality: '%s', size: '%s', model: '%s', is_edit: %s, num_input_images: %d",
                    img_prompt, img_quality, img_size, model, is_edit, num_images)
        
        # Use OpenAI client for Responses API
        client = self.openai_client
        
        # Prepare input for Responses API
        input_content = [{"type": "input_text", "text": img_prompt}]
        
        # Add input images if provided
        if image_inputs:
            for image_input in image_inputs:
                # Convert BytesIO to base64
                image_input.seek(0)
                image_bytes = image_input.read()
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # Determine MIME type from filename
                filename = getattr(image_input, 'name', 'image.png').lower()
                if filename.endswith('.jpg') or filename.endswith('.jpeg'):
                    mime_type = 'image/jpeg'
                elif filename.endswith('.webp'):
                    mime_type = 'image/webp'
                else:
                    mime_type = 'image/png'
                
                input_content.append({
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{image_base64}"
                })
        
        # Prepare tools configuration
        tools = [{
            "type": "image_generation",
            "partial_images": 2,  # Request 2 partial images
            "size": img_size,
            "quality": img_quality
        }]
        
        # Create streaming response
        stream = await asyncio.to_thread(
            lambda: client.responses.create(
                model="gpt-4o",  # Use supported model for Responses API
                input=[{
                    "role": "user",
                    "content": input_content
                }],
                tools=tools,
                stream=True
            )
        )
        
        # Track partial images and the single message
        partial_images = {}
        stream_message = None
        
        # Process streaming events as they arrive
        for event in stream:
            if event.type == "response.image_generation_call.partial_image":
                idx = event.partial_image_index
                image_base64 = event.partial_image_b64
                
                logger.info(f"Received partial image {idx}")
                
                # Store partial image
                partial_images[idx] = image_base64
                
                # Create Discord file and embed
                image_data = base64.b64decode(image_base64)
                file = discord.File(io.BytesIO(image_data), filename=f"generating_image.png")
                
                embed = discord.Embed(
                    title="Generating...", 
                    description=f"**Step {idx+1}**\n{img_prompt[:100]}{'...' if len(img_prompt) > 100 else ''}", 
                    color=0x32a956
                )
                embed.set_image(url=f"attachment://generating_image.png")
                embed.set_footer(text=f"GPT-image-1 | Streaming | Step {idx+1}")
                
                if stream_message is None:
                    # Send initial message
                    stream_message = await interaction.followup.send(file=file, embed=embed)
                    logger.info(f"Sent initial streaming message for partial {idx}")
                else:
                    # Edit existing message with new partial
                    try:
                        await stream_message.edit(embed=embed, attachments=[file])
                        logger.info(f"Updated streaming message with partial {idx}")
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                        logger.warning(f"Could not update streaming message with partial {idx}: {e}")
                        # Fallback: send new message
                        stream_message = await interaction.followup.send(file=file, embed=embed)
                
                # Yield control to allow other async operations
                await asyncio.sleep(0)
            
            elif event.type == "response.image_generation_call.completed":
                logger.info("Image generation completed - using latest partial image as final result")
                break
        
        # Calculate cost for streaming (since no usage info is returned)
        cost = self.calculate_image_cost("gpt-image-1", img_size, img_quality, is_edit)
        
        # Update the final message to show completion
        if stream_message:
            # Build standardized footer
            footer_text = self.build_footer(
                model="gpt-image-1",
                quality=img_quality,
                size=img_size,
                is_edit=is_edit,
                image_inputs=image_inputs,
                cost=cost,
                cost_source="estimated",
                generation_time=0,  # Streaming doesn't track time per message
                usage_info={}
            )
            
            try:
                # Get the current embed and update it to show completion
                if stream_message.embeds:
                    final_embed = stream_message.embeds[0]
                    # Update title to show completion
                    final_embed.title = "Generated"
                    # Update description to remove "Step X" 
                    final_embed.description = img_prompt[:100] + ('...' if len(img_prompt) > 100 else '')
                    # Update footer to remove streaming indicators
                    final_embed.set_footer(text=footer_text)
                    
                    # Use the latest partial image for the final version
                    if partial_images:
                        latest_idx = max(partial_images.keys())
                        latest_image_data = base64.b64decode(partial_images[latest_idx])
                        final_file = discord.File(io.BytesIO(latest_image_data), filename="generated_image.png")
                        final_embed.set_image(url="attachment://generated_image.png")
                        
                        await stream_message.edit(embed=final_embed, attachments=[final_file])
                        logger.info(f"Updated streaming message to show final completion")
                    else:
                        # Just update the embed without new attachment
                        await stream_message.edit(embed=final_embed)
                        logger.info(f"Updated streaming message embed to show completion")
                        
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                logger.warning(f"Could not update final streaming message: {e}")
        
        # Track usage in user quota system for streaming
        user_id = str(interaction.user.id)
        if cost > 0:
            if quota_manager.add_usage(user_id, cost):
                logger.info(f"Tracked ${cost:.4f} streaming image generation usage for user {user_id}")
            else:
                logger.warning(f"Failed to track streaming image generation usage for user {user_id}")
        
        # Return the latest partial image data
        if partial_images:
            latest_partial = partial_images[max(partial_images.keys())]
            return [f"data:image/png;base64,{latest_partial}"], {"total_cost": cost}
            
        return [], {"total_cost": cost}

    async def generate_image(self, img_prompt: str, img_quality: str, img_size: str, model: str = "dall-e-3", image_inputs: list = None, is_edit: bool = False):
        # Handle backwards compatibility
        if isinstance(image_inputs, io.BytesIO):
            image_inputs = [image_inputs]
        elif image_inputs is None:
            image_inputs = []
            
        num_images = len(image_inputs)
        logger.info("Entering generate_image function (COG) with prompt: '%s', quality: '%s', size: '%s', model: '%s', is_edit: %s, num_input_images: %d",
                    img_prompt, img_quality, img_size, model, is_edit, num_images)
        
        loop = asyncio.get_running_loop()
        
        # Always use OpenAI API for both DALL-E and GPT-image-1
        client = self.openai_client
        api_model = model
        
        if image_inputs and is_edit and model == "gpt-image-1":
            # Image editing with GPT-image-1 - use first image for editing
            primary_image = image_inputs[0]
            logger.info(f"Calling image edit with filename: {getattr(primary_image, 'name', 'unknown')}")
            if num_images > 1:
                logger.warning(f"GPT-image-1 edit mode only supports 1 image, ignoring {num_images - 1} additional images")
            response = await loop.run_in_executor(
                None,
                lambda: client.images.edit(
                    model=api_model,
                    image=primary_image,
                    prompt=img_prompt,
                    size=img_size,
                    quality=img_quality,
                    n=1,
                )
            )
        else:
            # Image generation (with or without image input for GPT-image-1)
            if model == "gpt-image-1":
                # GPT-image-1 supports using images as input for generation via the edit endpoint
                if image_inputs:
                    # Log input images being used
                    image_names = [getattr(img, 'name', 'unknown') for img in image_inputs]
                    logger.info(f"GPT-image-1 generation with {num_images} input images: {image_names}")
                    
                    # For GPT-image-1 with input images, use the edit endpoint even for "input" mode
                    # This allows the model to use the images as references for generation
                    response = await loop.run_in_executor(
                        None,
                        lambda: client.images.edit(
                            model=api_model,
                            image=image_inputs,  # Pass all input images
                            prompt=img_prompt,
                            size=img_size,
                            quality=img_quality,
                            n=1,
                        )
                    )
                else:
                    # No input images - standard generation
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
        quality="Image quality level",
        orientation="Choose the image orientation (Square, Landscape, or Portrait)",
        attachment="Optional input image",
        image_mode="How to use the attached image (only for GPT-image-1)",
        streaming="Enable partial image streaming (GPT-image-1 only)"
    )
    async def gen(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: Literal["dall-e-3", "gpt-image-1"] = "dall-e-3",
        quality: Literal["low", "high"] = "high",
        orientation: Literal["Square", "Landscape", "Portrait"] = "Square",
        attachment: Optional[discord.Attachment] = None,
        image_mode: Literal["input", "edit"] = "input",
        streaming: bool = False
    ):
        await interaction.response.defer(thinking=True)
        start_time = time.time()
        
        user_id = str(interaction.user.id)

        # Map quality parameter to API format
        if model == "gpt-image-1":
            # Two-tier mapping: low → medium, high → high
            api_quality = "high" if quality == "high" else "medium"
        else:
            # Two-tier mapping: low → standard, high → hd
            api_quality = "hd" if quality == "high" else "standard"
        
        # Different size support for different models
        if model == "gpt-image-1":
            # GPT-image-1 supports: 1024x1024, 1024x1536, 1536x1024, auto
            if orientation == "Landscape":
                size = "1536x1024"
            elif orientation == "Portrait":
                size = "1024x1536"
            else:
                size = "1024x1024"
        else:
            # DALL-E 3 supports: 1024x1024, 1024x1792, 1792x1024
            if orientation == "Landscape":
                size = "1792x1024"
            elif orientation == "Portrait":
                size = "1024x1792"
            else:
                size = "1024x1024"

            
        image_inputs = []
        is_edit = False
        
        # Collect all image attachments from the interaction message
        # Note: We need to get the message after the interaction to see all attachments
        try:
            # Get the original message that triggered this slash command
            # For slash commands, we need to check if there are additional attachments
            if attachment:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    if model != "gpt-image-1":
                        await interaction.followup.send("Image attachments are only supported with GPT-image-1 model.")
                        return
                    try:
                        image_bytes = await attachment.read()
                        image_input = io.BytesIO(image_bytes)
                        # Set the name attribute so OpenAI can determine the file type
                        image_input.name = attachment.filename
                        image_inputs.append(image_input)
                        is_edit = (image_mode == "edit")
                    except Exception as e:
                        logger.error(f"Error reading attachment: {e}")
                        await interaction.followup.send("Error reading image attachment. Please try again.")
                        return
                else:
                    await interaction.followup.send("Please attach a valid image file (PNG, JPG, JPEG, or WebP).")
                    return
            
            # Check for additional images in the message (Discord allows up to 10 attachments)
            # We need to fetch the actual message to see all attachments
            if interaction.message and hasattr(interaction.message, 'attachments'):
                for att in interaction.message.attachments:
                    if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and att != attachment:
                        if model != "gpt-image-1":
                            continue  # Skip additional images for non-GPT-image-1 models
                        try:
                            additional_bytes = await att.read()
                            additional_input = io.BytesIO(additional_bytes)
                            additional_input.name = att.filename
                            image_inputs.append(additional_input)
                            logger.info(f"Added additional image: {att.filename}")
                        except Exception as e:
                            logger.error(f"Error reading additional attachment {att.filename}: {e}")
                            
        except Exception as e:
            logger.error(f"Error processing attachments: {e}")
            
        # Log total images found
        if image_inputs:
            logger.info(f"Processing {len(image_inputs)} images for generation")

        # Check user quota before generating image (after collecting images for better cost estimation)
        remaining_quota = quota_manager.get_remaining_quota(user_id)
        num_input_images = len(image_inputs)
        
        # Estimate cost based on quality and multi-image operations
        base_cost = 0.20 if quality == "high" else 0.06
        estimated_cost = base_cost * 1.5 if num_input_images > 1 else base_cost
        
        if remaining_quota == 0:
            error_embed = create_error_embed("You've reached your monthly usage limit. Your quota resets at the beginning of each month.")
            await interaction.followup.send(embed=error_embed)
            return
        elif remaining_quota != float('inf') and remaining_quota < estimated_cost:
            cost_msg = f"${estimated_cost:.2f}" if num_input_images > 1 else "$0.04-$0.08"
            input_text = f"{num_input_images} input images" if num_input_images > 0 else "no input images"
            await interaction.followup.send(f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Image generation with {input_text} typically costs {cost_msg}.")
            return

        try:
            # Use streaming if enabled and model supports it
            if streaming and model == "gpt-image-1":
                result_urls, usage_info = await self.generate_image_streaming(
                    prompt, api_quality, size, model, image_inputs, is_edit, interaction
                )
                # Continue with normal flow to ensure image is properly sent
            else:
                result_urls, usage_info = await self.generate_image(prompt, api_quality, size, model, image_inputs, is_edit)
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
            cost = self.calculate_image_cost(model, size, api_quality, is_edit)
            cost_source = "estimated"
        
        # Track usage in user quota system
        if cost > 0:
            if quota_manager.add_usage(user_id, cost):
                logger.info(f"Tracked ${cost:.4f} image generation usage for user {user_id}")
            else:
                logger.warning(f"Failed to track image generation usage for user {user_id}")
        
        # Build standardized footer
        footer_text = self.build_footer(
            model=model,
            quality=api_quality,
            size=size,
            is_edit=is_edit,
            image_inputs=image_inputs,
            cost=cost,
            cost_source=cost_source,
            generation_time=generation_time,
            usage_info=usage_info
        )

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

    async def extract_images_from_message(self, message: discord.Message) -> list[io.BytesIO]:
        """Extract all images from a message (attachments and embeds)"""
        images = []
        
        # Check attachments first
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                try:
                    image_bytes = await attachment.read()
                    image_bytesio = io.BytesIO(image_bytes)
                    # Set the name attribute so OpenAI can determine the file type
                    image_bytesio.name = attachment.filename
                    images.append(image_bytesio)
                    logger.info(f"Extracted attachment image: {attachment.filename}")
                except Exception as e:
                    logger.error(f"Error reading attachment: {e}")
                    
        # Check embeds for images
        for i, embed in enumerate(message.embeds):
            if embed.image:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(embed.image.url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                image_bytesio = io.BytesIO(image_bytes)
                                # Extract filename from URL or use default .png
                                url = embed.image.url
                                if url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                    # Extract extension from URL
                                    extension = url.split('.')[-1].split('?')[0]  # Remove query params
                                    image_bytesio.name = f"embed_image_{i}.{extension}"
                                else:
                                    image_bytesio.name = f"embed_image_{i}.png"  # Default to PNG
                                images.append(image_bytesio)
                                logger.info(f"Extracted embed image: {image_bytesio.name}")
                except Exception as e:
                    logger.error(f"Error downloading embed image: {e}")
                    
        logger.info(f"Extracted {len(images)} images from message")
        return images
    
    async def extract_image_from_message(self, message: discord.Message) -> Optional[io.BytesIO]:
        """Extract first image from a message (backwards compatibility)"""
        images = await self.extract_images_from_message(message)
        return images[0] if images else None


class ImageEditModal(discord.ui.Modal):
    def __init__(self, image_cog: ImageGen, original_message: discord.Message):
        # Count images to customize title
        image_count = 0
        for att in original_message.attachments:
            if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                image_count += 1
        for embed in original_message.embeds:
            if embed.image:
                image_count += 1
        
        title = f'Generate with {image_count} Image{"s" if image_count > 1 else ""}'
        super().__init__(title=title)
        self.image_cog = image_cog
        self.original_message = original_message

    prompt = discord.ui.TextInput(
        label='Prompt',
        placeholder='Describe what you want to generate or how to edit this image...',
        required=True,
        max_length=1000
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
    
    quality = discord.ui.TextInput(
        label='Quality (low/high)',
        placeholder='high',
        default='high',
        required=False,
        max_length=10
    )
    

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = str(interaction.user.id)
        
        # Extract all images from original message first
        image_inputs = await self.image_cog.extract_images_from_message(self.original_message)
        if not image_inputs:
            await interaction.followup.send("No images found in the original message.")
            return
        
        # Check user quota before generating image (after we know how many images)
        remaining_quota = quota_manager.get_remaining_quota(user_id)
        num_input_images = len(image_inputs)
        
        # Get quality setting
        quality_str = self.quality.value.strip().lower() or "high"
        # Validate quality options - two-tier system
        if quality_str not in ("low", "high"):
            quality_str = "high"  # Default to high if invalid
        
        # Estimate cost based on quality and multi-image operations
        base_cost = 0.20 if quality_str == "high" else 0.06
        estimated_cost = base_cost * 1.5 if num_input_images > 1 else base_cost
        
        if remaining_quota == 0:
            error_embed = create_error_embed("You've reached your monthly usage limit. Your quota resets at the beginning of each month.")
            await interaction.followup.send(embed=error_embed)
            return
        elif remaining_quota != float('inf') and remaining_quota < estimated_cost:
            cost_msg = f"${estimated_cost:.2f}" if num_input_images > 1 else "$0.04-$0.08"
            await interaction.followup.send(f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. Image generation with {num_input_images} input images typically costs {cost_msg}.")
            return
            
        start_time = time.time()
        model_str = "gpt-image-1"
        orientation_str = self.orientation.value.strip().title() or "Square"
        image_mode_str = self.image_mode.value.strip().lower() or "input"
        use_streaming = True
        
        # Map quality to API format
        if model_str == "gpt-image-1":
            # Two-tier mapping: low → medium, high → high
            api_quality = "high" if quality_str == "high" else "medium"
        else:
            # Two-tier mapping: low → standard, high → hd
            api_quality = "hd" if quality_str == "high" else "standard"
        
        # Different size support for different models
        if model_str == "gpt-image-1":
            # GPT-image-1 supports: 1024x1024, 1024x1536, 1536x1024, auto
            if orientation_str == "Landscape":
                size = "1536x1024"
            elif orientation_str == "Portrait":
                size = "1024x1536"
            else:
                size = "1024x1024"
        else:
            # DALL-E 3 supports: 1024x1024, 1024x1792, 1792x1024
            if orientation_str == "Landscape":
                size = "1792x1024"
            elif orientation_str == "Portrait":
                size = "1024x1792"
            else:
                size = "1024x1024"
            
        is_edit = (image_mode_str == "edit")
            
        try:
            # Use streaming if enabled and model supports it
            if use_streaming and model_str == "gpt-image-1":
                result_urls, usage_info = await self.image_cog.generate_image_streaming(
                    self.prompt.value, api_quality, size, model_str, image_inputs, is_edit, interaction
                )
                # Continue with normal flow to ensure image is properly sent
            else:
                result_urls, usage_info = await self.image_cog.generate_image(self.prompt.value, api_quality, size, model_str, image_inputs, is_edit)
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
            cost = self.image_cog.calculate_image_cost(model_str, size, api_quality, is_edit)
            cost_source = "estimated"
        
        # Track usage in user quota system
        if cost > 0:
            if quota_manager.add_usage(user_id, cost):
                logger.info(f"Tracked ${cost:.4f} image generation usage for user {user_id}")
            else:
                logger.warning(f"Failed to track image generation usage for user {user_id}")
        
        # Build standardized footer
        footer_text = self.image_cog.build_footer(
            model=model_str,
            quality=api_quality,
            size=size,
            is_edit=is_edit,
            image_inputs=image_inputs,
            cost=cost,
            cost_source=cost_source,
            generation_time=generation_time,
            usage_info=usage_info
        )
        
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