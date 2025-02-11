import os
import asyncio
import logging
import openai
from discord.ext import commands
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class APIUtils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize API clients using environment variables.
        self.OAICLIENT = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.OPENROUTERCLIENT = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        # Global settings.
        self.SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
        self.BOT_TAG = os.getenv("BOT_TAG", "")
        self.FUN_SYSTEM_PROMPT = os.getenv("FUN_PROMPT", "Let's have some fun!")

    async def send_request(
        self,
        model: str,
        reply_mode: str,
        message_content: str,
        reference_message: str = None,
        image_url: str = None,
        custom_system_prompt: str = None,
        use_fun: bool = False,
    ) -> str:
        """
        Assemble a request payload and call the correct API.
        use_fun: If True, the call uses the openrouter client.
        """
        # Choose the right API client.
        api_client = self.OPENROUTERCLIENT if use_fun else self.OAICLIENT
        
        # Use the custom system prompt (if provided) or the default.
        system_used = custom_system_prompt if custom_system_prompt is not None else self.SYSTEM_PROMPT

        # Remove the bot tag from the user's message.
        message_content = message_content.replace(self.BOT_TAG, "")

        # Build up the messages payload.
        messages_input = [{"role": "system", "content": f"{system_used} {reply_mode}"}]
        if reference_message:
            messages_input.append({"role": "user", "content": reference_message})
        if image_url is None:
            messages_input.append({"role": "user", "content": message_content})
        else:
            messages_input.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": message_content},
                    {"type": "image_url", "image_url": image_url},
                ],
            })
        logger.info("Sending API request with payload: %s", messages_input)
        # Make the API call (wrapped in asyncio.to_thread so it doesn’t block the event loop)
        response = await asyncio.to_thread(
            api_client.chat.completions.create,
            model=model,
            messages=messages_input,
        )
        return response.choices[0].message.content

async def setup(bot: commands.Bot):
    await bot.add_cog(APIUtils(bot))