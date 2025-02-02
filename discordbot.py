import aiohttp
import discord
from discord.ext import commands
import openai
from openai import OpenAI
import os
from datetime import datetime
import time
import asyncio
from duckduckgo_search import DDGS  # NEW: for DDG search
from tenacity import ( AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential, )

# Import our consolidated embed helper and status updater.
from embed_utils import send_embed
from status_utils import update_status

# Set up API clients
openrouterclient = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
oaiclient = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Prompts and suffix definitions
o3mini_prompt = ""
concise_prompt = ("You are a concise and succinct assistant. When you aren't sure, do your best to guess "
                  "with ballpark figures or heuristic understanding. It is better to oversimplify than to give "
                  "a qualified answer. It is better to simply say you don't know than to explain nuance about the "
                  "question or its ambiguities.")
verbose_prompt = ("You are detailed & articulate. Include evidence and reasoning in your answers.")
creative_prompt = ("You are a creative chatbot. Do your best to suggest original ideas and avoid cliches. "
                   "Don't use overly poetic language. Be proactive and inventive and drive the conversation forward. "
                   "Never use the passive voice where you can use the active voice. Do not end your message with a summary.")

suffixes = {
    "-v": ("gpt-4o", verbose_prompt, "gpt-4o | Verbose"),
    "-c": ("gpt-4o", creative_prompt, "gpt-4o | Creative")
}

# Discord bot setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='!', intents=intents)

system_prompt = str(os.getenv("SYSTEM_PROMPT")).strip()
bot_tag = str(os.getenv("BOT_TAG")).strip()

reminders = [
    # e.g.: ('2024-04-17 03:50:00', 'Take out the garbage'),
]
reminders2 = {datetime.fromisoformat(rem[0]).timestamp(): rem[1] for rem in reminders}

def convert_to_readable(timestamp):
    """Convert Unix timestamp to human-readable format."""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

#######################################
# BACKGROUND REMINDER TASK
#######################################
async def background():
    reminder_times = list(reminders2.keys())
    while True:
        now = time.time()
        for t in reminder_times:
            if t in reminders2 and t < now:
                try:
                    user = await bot.fetch_user("195485849952059392")  # Replace with your own user ID.
                    print(f"Sending reminder to {user}: {reminders2[t]}")
                    await user.send(f"Reminder: {reminders2[t]}")
                except Exception as e:
                    print(f"Failed to send reminder: {e}")
                del reminders2[t]
                reminder_times.remove(t)
                break
        await asyncio.sleep(1)

#######################################
# HELPER FUNCTIONS
#######################################
async def delete_msg(msg):
    try:
        await msg.delete()
    except discord.errors.NotFound:
        print(f"Message {msg.id} not found.")
        pass

async def send_request(model, reply_mode, message_content, reference_message, image_url):
    print("Entering send_request function")
    # Remove the bot tag from the user message (if present)
    message_content = str(message_content).replace(bot_tag, "")
    messages_input = [{
        "role": "system",
        "content": system_prompt + " " + reply_mode
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
    print(f"Making API request (ref: {reference_message is not None}, image: {image_url is not None})")
    response = oaiclient.chat.completions.create(model=model, messages=messages_input)
    print("API request completed")
    return response.choices[0].message.content

async def generate_image(img_prompt, img_quality, img_size):
    print("Entering generate_image function")
    response = openai.images.generate(
        model="dall-e-3",
        prompt=img_prompt,
        size=img_size,
        quality=img_quality,
        n=1,
    )
    image_urls = [data.url for data in response.data]
    return image_urls

#######################################
# DDG SEARCH HELPER FUNCTIONS
#######################################
async def extract_search_query(user_message: str) -> str:
    """
    Uses GPT-4o-mini to extract a concise search query from the user’s message.
    """
    def _extract_search_query(um):
        try:
            response = oaiclient.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Extract a concise search query string from the following text that captures its key intent. Only return the query and nothing else."},
                    {"role": "user", "content": um},
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print("Error extracting search query:", e)
            return ""
    return await asyncio.to_thread(_extract_search_query, user_message)

async def perform_ddg_search(query: str) -> str:
    """
    Uses DuckDuckGo (via DDGS) to search for the given query and formats up to 10 results.
    """
    def _ddg_search(q):
        try:
            proxy = os.getenv("DUCK_PROXY")
            duck = DDGS(proxy=proxy) if proxy else DDGS()
            results = duck.text(q, max_results=10)
            return results
        except Exception as e:
            print("Error during DDG search:", e)
            return None
    results = await asyncio.to_thread(_ddg_search, query)
    if not results:
        return ""
    concat_result = f"Search query: {query}\n\n"
    for i, result in enumerate(results, start=1):
        title = result.get('title', '')
        body = result.get('body', '')
        concat_result += f"{i} -- {title}: {body}\n\n"
    return concat_result

#######################################
# DISCORD EVENTS AND COMMANDS
#######################################
@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        print(f"Bot is in server: {guild.name} (id: {guild.id})")
        member = guild.get_member(bot.user.id)
        if member:
            print(f"Bot's permissions in {guild.name}: {member.guild_permissions}")
    bot.loop.create_task(background())

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command()
async def rule(ctx):
    await ctx.send("")

@bot.command()
async def gen(ctx, *, prompt):
    start_time = time.time()
    # Default settings
    quality = "standard"
    size = "1024x1024"
    footer_text_parts = ["DALL·E 3"]
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
    prompt = " ".join(prompt_without_flags)
    
    status_msg = await update_status(None, "...generating image...", channel=ctx.channel)
    result_urls = await generate_image(prompt, quality, size)
    generation_time = round(time.time() - start_time, 2)
    footer_text_parts.append(f"generated in {generation_time} seconds")
    footer_text = " | ".join(footer_text_parts)
    await delete_msg(status_msg)
    
    for url in result_urls:
        embed = discord.Embed(title="", description=prompt, color=0x32a956)
        embed.set_footer(text=footer_text)
        await send_embed(ctx.channel, embed)

@bot.event
async def on_message(msg_rcvd):
    if msg_rcvd.author == bot.user:
        return

    if bot.user in msg_rcvd.mentions:
        # Set defaults.
        model, reply_mode, reply_mode_footer = "o3-mini", "o3mini_prompt", "o3-mini | default"
        start_time = time.time()
        # Start with a single status message
        status_msg = await update_status(None, "...reading request...", channel=msg_rcvd.channel)

        reference_author, reference_message, image_url = None, None, None

        if msg_rcvd.reference:
            try:
                if msg_rcvd.reference.cached_message:
                    ref_msg = msg_rcvd.reference.cached_message
                else:
                    ref_msg = await msg_rcvd.channel.fetch_message(msg_rcvd.reference.message_id)
                if ref_msg.author == bot.user:
                    status_msg = await update_status(status_msg, "...fetching bot reference...")
                    reference_message = ref_msg.embeds[0].description.strip() if ref_msg.embeds else ""
                else:
                    status_msg = await update_status(status_msg, "...fetching user reference...")
                reference_author = ref_msg.author.name
            except Exception:
                status_msg = await update_status(status_msg, "...unable to fetch reference...")

        if (msg_rcvd.attachments and msg_rcvd.attachments[0].filename.endswith(".txt")):
            attachment = msg_rcvd.attachments[0]
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        msg_rcvd.content = await response.text()
                    else:
                        status_msg = await update_status(status_msg, f"...failed to download attachment. Code: {response.status}")
                        
        if (msg_rcvd.attachments and any(msg_rcvd.attachments[0].filename.lower().endswith(ext)
                                         for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"])):
            image_url = msg_rcvd.attachments[0].url
            status_msg = await update_status(status_msg, "...analyzing image...")
            response = await send_request("gpt-4o", reply_mode, msg_rcvd.content.strip(), reference_message, image_url)
            await delete_msg(status_msg)
            response_embed = discord.Embed(title="", description=response, color=0x32a956)
            response_embed.set_footer(text=f"{reply_mode_footer} | generated in {round(time.time()-start_time, 2)} seconds")
            await send_embed(msg_rcvd.channel, response_embed, reply_to=msg_rcvd)
            return

        # Check for suffix flags in content (e.g. "-v" or "-c")
        if msg_rcvd.content[-2:] in suffixes:
            flag = msg_rcvd.content[-2:]
            msg_rcvd.content = msg_rcvd.content[:-2]
            model, reply_mode, reply_mode_footer = suffixes.get(flag, ("gpt-4o", "concise_prompt", "gpt-4o 'Concise'"))

        # NEW: DDG search integration.
        original_content = msg_rcvd.content.strip()
        status_msg = await update_status(status_msg, "...extracting search query...")
        search_query = await extract_search_query(original_content)
        
        if search_query:
            status_msg = await update_status(status_msg, "...searching the web...")
            ddg_results = await perform_ddg_search(search_query)
            if ddg_results:
                modified_message = original_content + "\n\nRelevant Internet Search Results:\n" + ddg_results
            else:
                modified_message = original_content
        else:
            modified_message = original_content

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((openai.APIError, openai.APIConnectionError, openai.RateLimitError)),
            wait=wait_exponential(min=1, max=10),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                print(f"Attempt {attempt.retry_state.attempt_number}/5 for request...")
                status_msg = await update_status(status_msg, "...generating reply...")
                response = await send_request(model, reply_mode, modified_message, reference_message, image_url)

        await delete_msg(status_msg)
        elapsed = round(time.time() - start_time, 2)
        response_embed = discord.Embed(title="", description=response, color=0x32a956)
        response_embed.set_footer(text=f"{reply_mode_footer} | generated in {elapsed} seconds")
        await send_embed(msg_rcvd.channel, response_embed, reply_to=msg_rcvd)

    await bot.process_commands(msg_rcvd)

#######################################
# RUN THE BOT
#######################################
async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

async def main():
    await load_cogs()
    await bot.start(os.getenv("BOT_API_TOKEN"))

asyncio.run(main())