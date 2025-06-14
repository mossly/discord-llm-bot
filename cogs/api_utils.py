import os
import asyncio
import logging
import openai
import discord
from discord.ext import commands
import base64
import aiohttp
import io
import re
from PIL import Image
from config_manager import config

logger = logging.getLogger(__name__)

class APIUtils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Initialize API clients using config manager
        api_config = config.get_api_clients_config()
        self.OAICLIENT = openai.OpenAI(api_key=api_config['openai_api_key'])
        self.OPENROUTERCLIENT = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_config['openrouter_api_key']
        )
        
        # Load system prompts from config manager
        self.SYSTEM_PROMPT = config.get_system_prompt(use_fun=False)
        self.FUN_SYSTEM_PROMPT = config.get_system_prompt(use_fun=True)
        self.BOT_TAG = config.get('bot_tag', '')

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
    
    def create_emoji_name_mapping(self, guild: discord.Guild) -> dict:
        """Create a mapping of emoji names to their proper Discord format"""
        if not guild or not guild.emojis:
            return {}
        
        emoji_mapping = {}
        for emoji in guild.emojis:
            if emoji.animated:
                emoji_mapping[emoji.name.lower()] = f"<a:{emoji.name}:{emoji.id}>"
            else:
                emoji_mapping[emoji.name.lower()] = f"<:{emoji.name}:{emoji.id}>"
        
        return emoji_mapping
    
    def substitute_emoji_formats(self, content: str, guild: discord.Guild) -> str:
        """Convert :emoji_name: format to proper <:emoji_name:id> format for server emojis"""
        if not content or not guild:
            return content
        
        # Get emoji name mapping
        emoji_mapping = self.create_emoji_name_mapping(guild)
        if not emoji_mapping:
            return content
        
        # Simple approach: find all :word: patterns and check if they're already formatted
        pattern = r':([a-zA-Z0-9_]+):'
        substitution_count = 0
        
        def replace_emoji(match):
            nonlocal substitution_count
            full_match = match.group(0)  # :word:
            emoji_name = match.group(1).lower()
            
            # Check if this is part of an already formatted emoji by looking at context
            start_pos = match.start()
            end_pos = match.end()
            
            # Look for < before the match (allowing for 'a:' in animated emojis)
            if start_pos > 0 and content[start_pos-1] == ':':
                # This might be part of <:name: or <a:name:
                if start_pos > 1 and content[start_pos-2] == 'a':
                    # Check for <a:
                    if start_pos > 2 and content[start_pos-3] == '<':
                        return full_match  # Already formatted animated emoji
                elif start_pos > 1 and content[start_pos-2] == '<':
                    # Check for <:
                    return full_match  # Already formatted emoji
            
            # Look for > after the match (indicating this is already formatted)
            if end_pos < len(content) and re.match(r'[0-9]+>', content[end_pos:]):
                return full_match  # Already formatted (has :id> after)
            
            # If emoji name matches a server emoji, convert it
            if emoji_name in emoji_mapping:
                logger.debug(f"Converting :{emoji_name}: to {emoji_mapping[emoji_name]}")
                substitution_count += 1
                return emoji_mapping[emoji_name]
            
            # Return original if not found (might be Unicode emoji)
            return full_match
        
        substituted_content = re.sub(pattern, replace_emoji, content)
        
        # Log if any substitutions were made
        if substitution_count > 0:
            logger.info(f"Made {substitution_count} emoji format substitutions")
        
        return substituted_content
    
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
        tool_choice: str = "auto",
        response_format: dict = None
    ) -> tuple:
        if api == "openrouter":
            api_client = self.OPENROUTERCLIENT
            logger.info(f"Using OpenRouter API for model: {model}")
        else:
            api_client = self.OAICLIENT
            logger.info(f"Using OpenAI API for model: {model}")
            
        if use_fun:
            base_system_prompt = self.FUN_SYSTEM_PROMPT
        else:
            base_system_prompt = self.SYSTEM_PROMPT
        
        # Add Discord context to system prompt if channel information is available
        system_used = base_system_prompt
        if emoji_channel and emoji_channel.guild:
            discord_context = f"\nCurrent Discord Context:\n"
            discord_context += f"Server ID: {emoji_channel.guild.id}\n"
            discord_context += f"Server Name: {emoji_channel.guild.name}\n"
            discord_context += f"Channel ID: {emoji_channel.id}\n"
            if hasattr(emoji_channel, 'name') and emoji_channel.name:
                discord_context += f"Channel Name: {emoji_channel.name}\n"
            discord_context += f"Channel Type: {emoji_channel.type}\n\n"
            system_used = base_system_prompt + discord_context
        
        message_content = message_content.replace(self.BOT_TAG, "")

        messages_input = [{"role": "system", "content": f"{system_used}"}]
        
        if use_emojis and emoji_channel:
            emoji_list = await self.get_guild_emoji_list(emoji_channel.guild)
            if emoji_list:
                emoji_content = f"""List of available custom emojis: {emoji_list}

        CRITICAL EMOJI RULES:
        - Use ONLY emojis from the above list with complete <:name:id> format
        - NEVER use :name: format - it will not work
        - Example: <:kibsmirk:1043092404959445013> ✅  vs :kibsmirk: ❌"""
                
                messages_input.append({"role": "system", "content": emoji_content})
                
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
            
            # Add response format if provided
            if response_format:
                request_params["response_format"] = response_format
            
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