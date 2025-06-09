import os
import asyncio
import logging
import openai
import discord
from discord.ext import commands
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
        # Load system prompts and prepend current datetime for LLM reference
        import datetime
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        datetime_prefix = f"Current date and time: {current_time}\n\n"
        
        base_system_prompt = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
        base_fun_prompt = os.getenv("FUN_PROMPT", "Write an amusing and sarcastic!")
        
        self.SYSTEM_PROMPT = datetime_prefix + base_system_prompt
        self.BOT_TAG = os.getenv("BOT_TAG", "")
        self.FUN_SYSTEM_PROMPT = datetime_prefix + base_fun_prompt

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
    
    async def fetch_generation_stats(self, generation_id: str) -> dict:
        logger.info(f"Fetching generation stats for ID: {generation_id}")
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
                    url = f"https://openrouter.ai/api/v1/generation?id={generation_id}"
                    
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            stats = await response.json()
                            logger.info(f"Successfully retrieved generation stats: {stats}")
                            return stats.get("data", {})
                        elif response.status == 404:
                            error_text = await response.text()
                            logger.warning(f"Generation stats not found on attempt {attempt+1}/{max_retries}: {error_text}")
                            
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                logger.warning(f"Failed to fetch generation stats after {max_retries} attempts")
                                return {}
                        else:
                            error_text = await response.text()
                            logger.error(f"Failed to fetch generation stats: HTTP {response.status}, {error_text}")
                            return {}
            except Exception as e:
                logger.exception(f"Error fetching generation stats on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return {}
        
        return {}
    
    async def send_request(
        self,
        model: str,
        message_content: str,
        reference_message: str = None,
        image_url: str = None,
        use_fun: bool = False,
        api: str = "openai",
        use_emojis: bool = False,
        emoji_channel: discord.TextChannel = None,
        max_tokens: int = 8000,
        tools: list = None,
        tool_choice: str = "auto"
    ) -> tuple:
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
        generation_stats = {}
        
        try:
            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages_input,
                "max_tokens": max_tokens
            }
            
            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = tool_choice
            
            response = await asyncio.to_thread(
                api_client.chat.completions.create,
                **request_params
            )
            
            if not response:
                logger.error("API returned None response")
                return "I'm sorry, I received an empty response from the API. Please try again.", {}
                
            if not hasattr(response, 'choices') or not response.choices:
                logger.error("API response missing choices: %s", response)
                return "I'm sorry, the API response was missing expected content. Please try again.", {}
                
            if not hasattr(response.choices[0], 'message') or not response.choices[0].message:
                logger.error("API response missing message in first choice: %s", response.choices[0])
                return "I'm sorry, the API response structure was unexpected. Please try again.", {}
                
            if not hasattr(response.choices[0].message, 'content'):
                logger.error("API response missing content in message: %s", response.choices[0].message)
                return "I'm sorry, the response content was missing. Please try again.", {}
            
            message = response.choices[0].message
            content = message.content
            
            # Check for tool calls
            tool_calls = None
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            
            if api == "openrouter" and hasattr(response, 'id'):
                generation_id = response.id
                logger.info(f"OpenRouter generation ID: {generation_id}")
                generation_stats = await self.fetch_generation_stats(generation_id)
            
            # Return content, stats, and tool_calls if any
            if tool_calls:
                return content, generation_stats, tool_calls
            else:
                return content, generation_stats
        except openai.APIStatusError as e:
            # Re-raise 402 errors to be handled by the caller
            if e.status_code == 402:
                logger.error(f"OpenRouter quota error (402): {e}")
                raise
            logger.exception("API Status Error in request: %s", e)
            return f"I'm sorry, there was an error communicating with the AI service: {str(e)}", {}
        except Exception as e:
            logger.exception("Error in API request: %s", e)
            return f"I'm sorry, there was an error communicating with the AI service: {str(e)}", {}
    
    async def send_request_with_tools(
        self,
        model: str,
        messages: list,
        tools: list = None,
        tool_choice: str = "auto",
        api: str = "openai",
        max_tokens: int = 8000
    ) -> dict:
        """Send request with tool support, returning structured response"""
        if api == "openrouter":
            api_client = self.OPENROUTERCLIENT
        else:
            api_client = self.OAICLIENT
        
        try:
            request_params = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens
            }
            
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = tool_choice
            
            response = await asyncio.to_thread(
                api_client.chat.completions.create,
                **request_params
            )
            
            if not response or not hasattr(response, 'choices') or not response.choices:
                return {"error": "Invalid API response"}
            
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": []
            }
            
            # Extract tool calls
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            
            # Get usage stats for OpenRouter
            if api == "openrouter" and hasattr(response, 'id'):
                stats = await self.fetch_generation_stats(response.id)
                result["stats"] = stats
            elif hasattr(response, 'usage'):
                # Standard OpenAI usage format
                result["stats"] = {
                    "tokens_prompt": response.usage.prompt_tokens,
                    "tokens_completion": response.usage.completion_tokens,
                    "tokens_total": response.usage.total_tokens
                }
            
            return result
            
        except Exception as e:
            logger.exception(f"Error in tool request: {e}")
            return {"error": str(e)}

async def setup(bot: commands.Bot):
    await bot.add_cog(APIUtils(bot))