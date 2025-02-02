import aiohttp
import discord
from discord.ext import commands
import openai
from openai import OpenAI
import os
from datetime import datetime
import time
import asyncio

# Configure your OpenAI clients
  openrouterclient = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv("OPENROUTER_API_KEY"),
)

oaiclient = OpenAI(
  api_key=os.getenv("OPENAI_API_KEY"),
)

# Prompts and suffixes
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
    "-v": ("gpt-4o", verbose_prompt, "gpt-4o 'Verbose'"),
    "-c": ("gpt-4o", creative_prompt, "gpt-4o 'Creative'")
}

# Discord bot setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)
global bot
bot = commands.Bot(command_prefix='!', intents=intents)

system_prompt = str(os.getenv("SYSTEM_PROMPT")).strip()
bot_tag = str(os.getenv("BOT_TAG")).strip()

reminders = [
    # ('2024-04-17 03:50:00', 'Take out the garbage'),
]

# Convert reminder dates into Unix timestamps
reminders2 = {datetime.fromisoformat(reminder[0]).timestamp(): reminder[1] for reminder in reminders}

def convert_to_readable(timestamp):
    """Converts Unix timestamp to human-readable format."""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

###############################
# EMBED UTILITY FUNCTIONS
###############################
def get_embed_total_length(embed: discord.Embed) -> int:
    """Calculate the total number of characters used in an embed."""
    total = 0
    if embed.title:
        total += len(embed.title)
    if embed.description:
        total += len(embed.description)
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    for field in embed.fields:
        total += len(field.name) + len(field.value)
    return total

def split_embed(embed: discord.Embed) -> list:
    """
    Splits an embed into multiple embeds if its description exceeds limits.
    
    Discord’s limits:
      • Total embed content must be <= 6000 characters.
      • Description is limited to 4096 characters.
      
    This function splits the embed’s description into chunks that are safely within these limits.
    The first embed gets the original title (if any) and the final embed gets the original footer (if any).
    """
    # Calculate header and footer lengths (default to 0 if not present)
    header_len = len(embed.title) if embed.title else 0
    footer_len = len(embed.footer.text) if (embed.footer and embed.footer.text) else 0
    # For safety, we’ll use a chunk size that is the lower of:
    #   • The description’s hard limit (4096)
    #   • The overall embed limit minus the maximum overhead (from title or footer)
    safe_chunk_size = min(4096, 6000 - max(header_len, footer_len))
    
    text = embed.description if embed.description else ""
    # If there is no text, return the original embed.
    if not text:
        return [embed]
    
    # Split the description into successive chunks
    chunks = [text[i:i+safe_chunk_size] for i in range(0, len(text), safe_chunk_size)]
    new_embeds = []
    for idx, chunk in enumerate(chunks):
        new_embed = discord.Embed(color=embed.color)
        # Only the first embed gets the title.
        if idx == 0 and embed.title:
            new_embed.title = embed.title
        new_embed.description = chunk
        # The last embed gets the footer.
        if idx == len(chunks) - 1 and embed.footer and embed.footer.text:
            new_embed.set_footer(text=embed.footer.text)
        new_embeds.append(new_embed)
    return new_embeds

async def send_embed_reply(message: discord.Message, embed: discord.Embed):
    """
    Sends an embed reply to a message.
    If the embed's content exceeds Discord’s limits, split it into multiple messages.
    """
    # Check if the embed’s description or overall size is too long.
    if (embed.description and len(embed.description) > 4096) or get_embed_total_length(embed) > 6000:
        embeds = split_embed(embed)
        # Reply with the first embed...
        await message.reply(embed=embeds[0])
        # ...and send any additional embeds into the channel.
        for e in embeds[1:]:
            await message.channel.send(embed=e)
    else:
        await message.reply(embed=embed)

###############################
# BACKGROUND REMINDER TASK
###############################
async def background():
    reminder_times = list(reminders2.keys())
    while True:
        now = time.time()
        for timestamp in reminder_times:
            if timestamp in reminders2:
                if timestamp < now:
                    try:
                        user = await bot.fetch_user("195485849952059392")  # Replace with your user ID
                        print(f'Sent {user} reminder: {reminders2[timestamp]}')
                        await user.send(f"Reminder: {reminders2[timestamp]}")
                    except Exception as e:
                        print(f"Failed to send reminder: {e}")
                    del reminders2[timestamp]
                    reminder_times.remove(timestamp)
                    break  # Exit loop and wait for next cycle
        await asyncio.sleep(1)

###############################
# HELPER FUNCTIONS
###############################
async def delete_msg(msg):
    try:
        await msg.delete()
    except discord.errors.NotFound:
        print(f'msg {msg.id} not found')
        pass

async def send_request(model, reply_mode, message_content, reference_message, image_url):
    print("Entering send_request function")
    # Remove bot mention tag if present
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
    print(f"About to make API request with reference message [{reference_message is not None}] and image [{image_url is not None}]")
    response = oaiclient.chat.completions.create(model=model, messages=messages_input)
    print(f"API request completed with reference message [{reference_message is not None}] and image [{image_url is not None}]")
    return response.choices[0].message.content

async def generate_image(img_prompt, img_quality, img_size):
    print("Entering gen_image function")
    response = openai.images.generate(
        model="dall-e-3",
        prompt=img_prompt,
        size=img_size,
        quality=img_quality,
        n=1,
    )
    image_urls = [data.url for data in response.data]
    return image_urls

###############################
# DISCORD EVENTS AND COMMANDS
###############################
@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord!")
    for guild in bot.guilds:
        print(f"Bot is in server: {guild.name} (id: {guild.id})")
        member = guild.get_member(bot.user.id)
        if member:
            permissions = member.guild_permissions
            print(f"Bot's permissions in {guild.name}: {permissions}")
    bot.loop.create_task(background())

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

@bot.command()
async def rule(ctx):
    await ctx.send()

@bot.command()
async def gen(ctx, *, prompt):
    start_time = time.time()
    # Default image generation settings:
    quality = "standard"
    size = "1024x1024"
    footer_text_parts = ["DALL·E 3"]
    # Parse prompt flags
    args = prompt.split()
    prompt_without_flags = []
    for index, arg in enumerate(args):
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
    status_msg = await ctx.send(embed=discord.Embed(title="", description="...generating image...", color=0xFDDA0D))
    result_urls = await generate_image(prompt, quality, size)
    generation_time = round(time.time() - start_time, 2)
    footer_text_parts.append(f"generated in {generation_time} seconds")
    footer_text = " | ".join(footer_text_parts)
    await delete_msg(status_msg)
    for url in result_urls:
        embed = discord.Embed(title="", description=prompt, color=0x32a956)
        embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

async def temp_msg(replaces_msg, request_msg, embed):
    if replaces_msg:
        await delete_msg(replaces_msg)
    return await request_msg.reply(embed=embed)

@bot.event
async def on_message(msg_rcvd):
    if msg_rcvd.author == bot.user:
        return

    if bot.user in msg_rcvd.mentions:
        model, reply_mode, reply_mode_footer = "o3-mini", "o3mini_prompt", "o3-mini | default"
        start_time = time.time()
        # Send an initial status message
        status_embed = discord.Embed(title="", description="...reading request...", color=0xFDDA0D)
        status_embed.set_footer(text="")
        status_msg = await temp_msg(None, msg_rcvd, status_embed)

        reference_author, reference_message, image_url = None, None, None

        # Check for reference message (reply chain)
        if msg_rcvd.reference:
            try:
                ref_msg = None
                if msg_rcvd.reference.cached_message:
                    ref_msg = msg_rcvd.reference.cached_message
                else:
                    ref_msg = await msg_rcvd.channel.fetch_message(msg_rcvd.reference.message_id)

                if ref_msg.author == bot.user:
                    status_embed = discord.Embed(title="", description="...fetching bot reference...", color=0xFDDA0D)
                    status_embed.set_footer(text="")
                    status_msg = await temp_msg(status_msg, msg_rcvd, status_embed)
                    reference_message = ref_msg.embeds[0].description.strip()
                else:
                    status_embed = discord.Embed(title="", description="...fetching user reference...", color=0xFDDA0D)
                    status_embed.set_footer(text="")
                    status_msg = await temp_msg(status_msg, msg_rcvd, status_embed)
                reference_author = ref_msg.author.name
            except AttributeError:
                status_embed = discord.Embed(title="", description="...unable to fetch reference, the message is not cached...", color=0xFDDA0D)
                status_embed.set_footer(text="")
                status_msg = await temp_msg(status_msg, msg_rcvd, status_embed)

        # If a .txt file is attached, download it and set msg content accordingly.
        if (msg_rcvd.attachments and msg_rcvd.attachments[0].filename.endswith(".txt")):
            attachment = msg_rcvd.attachments[0]
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        msg_rcvd.content = await response.text()
                    else:
                        error_embed = discord.Embed(title="ERROR", description="x_x", color=0x32a956)
                        error_embed.set_footer(text=f"...failed to download the attached .txt file... code: {response.status}")
                        status_msg = await temp_msg(status_msg, msg_rcvd, error_embed)

        # If an image attachment is present, grab its URL and process it
        if (msg_rcvd.attachments and any(msg_rcvd.attachments[0].filename.endswith(x) for x in [".png", ".jpg", ".jpeg", ".webp", ".gif"])):
            image_url = msg_rcvd.attachments[0].url
            status_embed = discord.Embed(title="", description="...analyzing image...", color=0xFDDA0D)
            status_embed.set_footer(text="")
            status_msg = await temp_msg(status_msg, msg_rcvd, status_embed)
            response = await send_request("gpt-4o", reply_mode, msg_rcvd.content.strip(), reference_message, image_url)
            await delete_msg(status_msg)
            response_embed = discord.Embed(title="", description=response, color=0x32a956)
            response_embed.set_footer(text=f'{reply_mode_footer} | generated in {round(time.time() - start_time, 2)} seconds')
            await send_embed_reply(msg_rcvd, response_embed)
            return

        # Check for suffix flags in the message content
        if msg_rcvd.content[-2:] in suffixes:
            msg_rcvd.content = msg_rcvd.content[:-2]
            model, reply_mode, reply_mode_footer = suffixes.get(msg_rcvd.content[-2:], ("gpt-4o", "concise_prompt", "gpt-4o 'Concise'"))
        
        status_embed = discord.Embed(title="", description="...generating reply...", color=0xFDDA0D)
        status_embed.set_footer(text="")
        status_msg = await temp_msg(status_msg, msg_rcvd, status_embed)

        max_retries = 5
        for retry in range(max_retries):
            try:
                print("Trying for " + str(retry) + "/" + str(max_retries) + "...")
                response = await send_request(model, reply_mode, msg_rcvd.content.strip(), reference_message, image_url)
            except openai.APIError as e:
                if retry == max_retries - 1:
                    error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                    error_embed.set_footer(text=f"OpenAI API returned an API Error: {e}")
                    await temp_msg(status_msg, msg_rcvd, error_embed)
                continue
            except openai.APIConnectionError as e:
                if retry == max_retries - 1:
                    error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                    error_embed.set_footer(text=f"Failed to connect to OpenAI API: {e}")
                    await temp_msg(status_msg, msg_rcvd, error_embed)
                continue
            except openai.RateLimitError as e:
                if retry == max_retries - 1:
                    error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
                    error_embed.set_footer(text=f"OpenAI API request exceeded rate limit: {e}")
                    await temp_msg(status_msg, msg_rcvd, error_embed)
                continue
            else:
                await delete_msg(status_msg)
                response_embed = discord.Embed(title="", description=response, color=0x32a956)
                response_embed.set_footer(text=f'{reply_mode_footer} | generated in {round(time.time() - start_time, 2)} seconds')
                await send_embed_reply(msg_rcvd, response_embed)
                break
    await bot.process_commands(msg_rcvd)

###############################
# RUN THE BOT
###############################
BOTAPITOKEN = os.getenv("BOT_API_TOKEN")
bot.run(BOTAPITOKEN)
