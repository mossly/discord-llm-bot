from discord.ext import commands
import discord
import time
import asyncio
from datetime import datetime
import openai
from openai import OpenAI
import os
from tenacity import (AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential)
from embed_utils import send_embed
from status_utils import update_status
from message_utils import delete_msg

class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Set up your API clients here (or import them if you’re using a shared module)
        self.oaiclient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.openrouterclient = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
        self.system_prompt = str(os.getenv("SYSTEM_PROMPT")).strip()
        self.bot_tag = str(os.getenv("BOT_TAG")).strip()

        # You can store model settings or prompts here.
        self.suffixes = {
            "-o3": ("gpt-4o", "verbose_prompt", "gpt-4o | Verbose"),
            "-4o": ("gpt-4o", "creative_prompt", "gpt-4o | Creative")
        }

    async def send_request(self, model, reply_mode, message_content, reference_message, image_url):
        # Remove the bot tag from the user message, etc.
        message_content = str(message_content).replace(self.bot_tag, "")
        messages_input = [{
            "role": "system",
            "content": self.system_prompt + " " + reply_mode
        }]
        if reference_message is not None:
            messages_input.append({"role": "user", "content": reference_message})
        user_message = {
            "role": "user",
            "content": message_content if image_url is None else [
                {"type": "text", "text": message_content},
                {"type": "image_url", "image_url": image_url}
            ]
        }
        messages_input.append(user_message)
        response = self.oaiclient.chat.completions.create(model=model, messages=messages_input)
        return response.choices[0].message.content

    @commands.Cog.listener()
    async def on_message(self, msg_rcvd):
        # Make sure we ignore our own messages.
        if msg_rcvd.author == self.bot.user:
            return

        # Check if we are mentioned.
        if self.bot.user in msg_rcvd.mentions:
            start_time = time.time()
            status_msg = await update_status(None, "...reading request...", channel=msg_rcvd.channel)

            reference_message = None
            image_url = None

            # Handle message reference if present.
            if msg_rcvd.reference:
                try:
                    ref_msg = (msg_rcvd.reference.cached_message or
                               await msg_rcvd.channel.fetch_message(msg_rcvd.reference.message_id))
                    if ref_msg.author == self.bot.user and ref_msg.embeds:
                        status_msg = await update_status(status_msg, "...fetching bot reference...")
                        reference_message = ref_msg.embeds[0].description.strip()
                    else:
                        status_msg = await update_status(status_msg, "...fetching user reference...")
                except Exception:
                    status_msg = await update_status(status_msg, "...unable to fetch reference...")

            # Process attachments if any.
            if msg_rcvd.attachments:
                first_attachment = msg_rcvd.attachments[0]
                if first_attachment.filename.endswith(".txt"):
                    async with self.bot.http_session.get(first_attachment.url) as response:
                        if response.status == 200:
                            msg_rcvd.content = await response.text()
                        else:
                            status_msg = await update_status(
                                status_msg, f"...failed to download attachment. Code: {response.status}"
                            )
                elif any(first_attachment.filename.lower().endswith(ext)
                         for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                    image_url = first_attachment.url
                    status_msg = await update_status(status_msg, "...analyzing image...")
                    response_text = await self.send_request("gpt-4o", "default", msg_rcvd.content.strip(), reference_message, image_url)
                    await delete_msg(status_msg)
                    response_embed = discord.Embed(description=response_text, color=0x32a956)
                    elapsed = round(time.time() - start_time, 2)
                    response_embed.set_footer(text=f"gpt-4o | generated in {elapsed} seconds")
                    await send_embed(msg_rcvd.channel, response_embed, reply_to=msg_rcvd)
                    return

            # Check for flag suffixes.
            model, reply_mode, footer_text = "o3-mini", "o3mini_prompt", "o3-mini | default"
            if msg_rcvd.content.strip()[-2:] in self.suffixes:
                flag = msg_rcvd.content.strip()[-2:]
                msg_rcvd.content = msg_rcvd.content.strip()[:-2]
                model, reply_mode, footer_text = self.suffixes[flag]

            # (Optional) Integrate DuckDuckGo search if your bot’s DuckDuckGo cog is loaded.
            modified_message = msg_rcvd.content.strip()
            ddg_cog = self.bot.get_cog("DuckDuckGo")
            if ddg_cog:
                status_msg = await update_status(status_msg, "...extracting search query...")
                search_query = await ddg_cog.extract_search_query(modified_message)
                if search_query:
                    status_msg = await update_status(status_msg, "...searching the web...")
                    ddg_results = await ddg_cog.perform_ddg_search(search_query)
                    if ddg_results:
                        modified_message += "\n\nRelevant Internet Search Results:\n" + ddg_results

            # Use tenacity to retry API requests if necessary.
            for attempt in AsyncRetrying(
                retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
                wait=wait_exponential(min=1, max=10),
                stop=stop_after_attempt(5),
                reraise=True,
            ):
                async with attempt:
                    status_msg = await update_status(status_msg, "...generating reply...")
                    response_text = await self.send_request(model, reply_mode, modified_message, reference_message, image_url)

            await delete_msg(status_msg)
            elapsed = round(time.time()-start_time, 2)
            response_embed = discord.Embed(description=response_text, color=0x32a956)
            response_embed.set_footer(text=f"{footer_text} | generated in {elapsed} seconds")
            await send_embed(msg_rcvd.channel, response_embed, reply_to=msg_rcvd)

        # Allow other commands to be processed.
        await self.bot.process_commands(msg_rcvd)

async def setup(bot):
    await bot.add_cog(ChatCog(bot))