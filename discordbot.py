import requests
import os
import time
import discord
from discord.ext import commands
import openai

concise_prompt = "You are a concise and succinct assistant. When you aren't sure, do your best to guess with ballpark figures or heuristic understanding. It is better to oversimplify than to give a qualified answer. It is better to simply say you don't know than to explain nuance about the question or its ambiguities."
verbose_prompt = "You are detailed & articulate. Include evidence and reasoning in your answers."
creative_prompt = "You are a creative chatbot. Do your best to suggest original ideas and avoid cliches. Don't use overly poetic language. Be proactive and inventive and drive the conversation forward. Never use the passive voice where you can use the active voice. Do not end your message with a summary."

intents = discord.Intents.default()
intents.typing = True
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

openai.api_key = os.getenv("OPENAI_API_KEY")
system_prompt = str(os.getenv("SYSTEM_PROMPT")).strip()
bot_tag = str(os.getenv("BOT_TAG")).strip()

async def send_request(model, reply_mode, message_content, reference_message):
    message_content = str(message_content).replace(bot_tag, "")
    
    if reference_message is None:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt+" "+reply_mode},
                {"role": "user", "content": message_content},
            ]
        )
    else:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt+" "+reply_mode},
                {"role": "user", "content": reference_message},
                {"role": "user", "content": message_content},
            ]
        )
    return response

@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        start_time = time.time()
        temp_message = await message.reply(embed=discord.Embed(title="", description="...reading request...", color=0xFDDA0D).set_footer(text=""))
        
        reference_author = None
        reference_message = None
        
        if message.reference:
            try:
                if message.reference.cached_message.author == bot.user:
                    await temp_message.delete()
                    temp_message = await message.reply(embed=discord.Embed(title="", description="...fetching bot reference...", color=0xFDDA0D).set_footer(text=""))
                    reference_message = message.reference.cached_message.embeds[0].description.strip()
                else:
                    await temp_message.delete()
                    temp_message = await message.reply(embed=discord.Embed(title="", description="...fetching user reference...", color=0xFDDA0D).set_footer(text=""))
                    reference_message = message.reference.cached_message.content.strip()
                reference_author = message.reference.cached_message.author.name
            except AttributeError:
                await temp_message.delete()
                temp_message = await message.reply(embed=discord.Embed(title="", description="...unable to fetch reference, the message is not cached...", color=0x32a956).set_footer(text='Error | generated in {round(time.time() - start_time, 2)} seconds'))

            suffixes = {
                "-v": ("gpt-4", verbose_prompt),
                "-t": ("gpt-3.5-turbo", concise_prompt),
                "-c": ("gpt-4", creative_prompt)
            }

            model, reply_mode = suffixes.get(message.content[-2:], ("gpt-4", "concise_prompt"))
        
        if message.content[-2:] in suffixes:
            message.content = message.content[:-2]

        await temp_message.delete()
        temp_message = await message.reply(embed=discord.Embed(title="", description="...generating reply...", color=0xFDDA0D).set_footer(text=""))
        
        max_retries = 5
        for retry in range(max_retries):
            try:
                #Make your OpenAI API request here
                response = await send_request(model, reply_mode, message.content.strip(), reference_message)
            except openai.error.APIError as e:
                #Handle API error here, e.g. retry or log
                if retry == max_retries - 1: 
                    await temp_message.delete()
                    await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"OpenAI API returned an API Error: {e}"))
                continue
            except openai.error.APIConnectionError as e:
                if retry == max_retries - 1: 
                    await temp_message.delete()
                    await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"Failed to connect to OpenAI API: {e}"))
                continue
            except openai.error.RateLimitError as e:
                if retry == max_retries - 1: 
                    await temp_message.delete()
                    await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"OpenAI API request exceeded rate limit: {e}"))
                continue
            else:
                await temp_message.delete()
                await message.reply(embed=discord.Embed(title="", description=response['choices'][0]['message']['content'].strip(), color=0x32a956).set_footer(text=f'{model} {reply_mode} | generated in {round(time.time() - start_time, 2)} seconds'))
    
BOTAPITOKEN  = os.getenv("BOT_API_TOKEN")

bot.run(BOTAPITOKEN)
