import os
import asyncio
import logging
import openai
import discord
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import base64
import aiohttp
import io
from PIL import Image

logger = logging.getLogger(__name__)

class APIUtils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.OAICLIENT = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.OPENROUTERCLIENT = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
        self.BOT_TAG = os.getenv("BOT_TAG", "")
        self.FUN_SYSTEM_PROMPT = os.getenv("FUN_PROMPT", "Write an amusing and sarcastic!")

    async def get_guild_emoji_list(self, guild: discord.Guild) -> str:
        if not guild or not guild.emojis:
            logger.info("No guild or no emojis found in guild")
            return ""
        emoji_list = []
        for emoji in guild.emojis:
            if emoji.animated:
                emoji_list.append(f"<a:{emoji.name}:{emoji.id}>")
            else:
                emoji_list.append(f"<:{emoji.name}:{emoji.id}>")
        emoji_string = ",".join(emoji_list)
        logger.info(f"Compiled emoji list with {len(emoji_list)} emojis")
        return emoji_string
    
    async def send_request(
        self,
        model: str,
        message_content: str,
        reference_message: str = None,
        image_url: str = None,
        use_fun: bool = False,
        api: str = "openai",
        use_emojis: bool = False,
        emoji_channel: discord.TextChannel = None
    ) -> str:
        if api == "openrouter":
            api_client = self.OPENROUTERCLIENT
            logger.info(f"Using OpenRouter API for model: {model}")
        else:
            api_client = self.OAICLIENT
            logger.info(f"Using OpenAI API for model: {model}")
            
        if use_fun:
            system_used = self.FUN_SYSTEM_PROMPT
        else:
            system_used = self.SYSTEM_PROMPT
        
        message_content = message_content.replace(self.BOT_TAG, "")

        messages_input = [{"role": "system", "content": f"{system_used}"}]
        
        if use_emojis and emoji_channel:
            emoji_list = await self.get_guild_emoji_list(emoji_channel.guild)
            if emoji_list:
                messages_input.append({"role": "system", "content": f"List of available custom emojis: {emoji_list}"})
        
        if reference_message:
            messages_input.append({"role": "user", "content": reference_message})
        
        if image_url is None:
            messages_input.append({"role": "user", "content": message_content})
        else:
            try:
                content_list = [{"type": "text", "text": message_content}]
                
                if image_url and ("cdn.discordapp.com" in image_url or "media.discordapp.net" in image_url):
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as response:
                            if response.status == 200:
                                image_bytes = await response.read()
                                if image_url.lower().endswith('.png'):
                                    mime_type = 'image/png'
                                elif image_url.lower().endswith(('.jpg', '.jpeg')):
                                    mime_type = 'image/jpeg'
                                elif image_url.lower().endswith('.webp'):
                                    mime_type = 'image/webp'
                                elif image_url.lower().endswith('.gif'):
                                    mime_type = 'image/gif'
                                else:
                                    mime_type = 'image/jpeg'
                                
                                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                                content_list.append({
                                    "type": "image_url", 
                                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                                })
                    
                messages_input.append({"role": "user", "content": content_list})
            except Exception as e:
                logger.exception(f"Error processing image: {e}")
                messages_input.append({"role": "user", "content": message_content})
        
        logger.info("Sending API request with payload: %s", messages_input)
        
        try:
            response = await asyncio.to_thread(
                api_client.chat.completions.create,
                model=model,
                messages=messages_input,
            )
            
            # Validate response before accessing properties
            if not response:
                logger.error("API returned None response")
                return "I'm sorry, I received an empty response from the API. Please try again."
                
            if not hasattr(response, 'choices') or not response.choices:
                logger.error("API response missing choices: %s", response)
                return "I'm sorry, the API response was missing expected content. Please try again."
                
            if not hasattr(response.choices[0], 'message') or not response.choices[0].message:
                logger.error("API response missing message in first choice: %s", response.choices[0])
                return "I'm sorry, the API response structure was unexpected. Please try again."
                
            if not hasattr(response.choices[0].message, 'content'):
                logger.error("API response missing content in message: %s", response.choices[0].message)
                return "I'm sorry, the response content was missing. Please try again."
                
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("Error in API request: %s", e)
            return f"I'm sorry, there was an error communicating with the AI service: {str(e)}"

async def setup(bot: commands.Bot):
    await bot.add_cog(APIUtils(bot))