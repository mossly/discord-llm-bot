import requests
import os
import time
import discord
from discord.ext import commands
import openai

intents = discord.Intents.default()
intents.typing = True
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

openai.api_key = os.getenv("OPENAI_API_KEY")

@bot.event
async def on_ready():
    print(f"{bot.user.name} has connected to Discord!")

async def send_request(model, message_content):
  openai.ChatCompletion.create(
    model=model,
    messages=[
          {"role": "system", "content": "You are MS-DOS-LY, a concise and succinct assistant. When you aren't sure, do your best to guess with ballpark figures or heuristic understanding. It is better to oversimplify than to give a qualified answer. It is better to simply say you don't know than to explain nuance about the question or its ambiguities."},
          {"role": "user", "content": str(message_content).replace("<@1088294375253082223>", "")},
      ]
  )

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
            if message.reference.cached_message.author == bot.user:
                await temp_message.delete()
                temp_message = await message.reply(embed=discord.Embed(title="", description="...fetching bot reference...", color=0xFDDA0D).set_footer(text=""))
                reference_message = message.reference.cached_message.embeds[0].description
                reference_author = "MS-DOS-LY"
            else:
                await temp_message.delete()
                temp_message = await message.reply(embed=discord.Embed(title="", description="...fetching user reference...", color=0xFDDA0D).set_footer(text=""))
                reference_message = message.reference.cached_message.content
                reference_author = message.reference.cached_message.author.name
            
        suffixes = {
            "-v": ("gpt-4", "Verbose"),
            "-t": ("gpt-3.5-turbo", "Concise"),
            "-c": ("gpt-4", "Creative")
        }

        model, replyMode = suffixes.get(message.content[-2:], ("gpt-4", "Concise"))
        
        if message.content[-2:] in suffixes:
            message.content = message.content[:-2]

        await temp_message.delete()
        
        temp_message = await message.reply(embed=discord.Embed(title="", description="...generating reply...", color=0xFDDA0D).set_footer(text=""))
        
        response = await send_request(model, message.content.strip())
        
        await temp_message.delete()

        try:
            #Make your OpenAI API request here
            response = await send_request(model, message.content.strip())
        except openai.error.APIError as e:
            #Handle API error here, e.g. retry or log
            await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"OpenAI API returned an API Error: {e}"))
            pass
        except openai.error.APIConnectionError as e:
            #Handle connection error here
            await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"Failed to connect to OpenAI API: {e}"))
            pass
        except openai.error.RateLimitError as e:
            #Handle rate limit error (we recommend using exponential backoff)
            await message.reply(embed=discord.Embed(title="ERROR", description="x_x", color=0xDC143C).set_footer(text=f"OpenAI API request exceeded rate limit: {e}"))
            pass
        else:
            await message.reply(embed=discord.Embed(title="", description=response['choices'][0]['message']['content'].strip(), color=0x32a956).set_footer(text=f'{replyMode} | generated in {round(time.time() - start_time, 2)} seconds'))

BOTAPITOKEN  = os.getenv("BOT_API_TOKEN")

bot.run(BOTAPITOKEN)
