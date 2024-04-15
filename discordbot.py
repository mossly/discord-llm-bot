import aiohttp
import discord
from discord.ext import commands
import openai
from openai import OpenAI
import os
import time

oaiclient = OpenAI()

concise_prompt = "You are a concise and succinct assistant. When you aren't sure, do your best to guess with ballpark figures or heuristic understanding. It is better to oversimplify than to give a qualified answer. It is better to simply say you don't know than to explain nuance about the question or its ambiguities."
verbose_prompt = "You are detailed & articulate. Include evidence and reasoning in your answers."
creative_prompt = "You are a creative chatbot. Do your best to suggest original ideas and avoid cliches. Don't use overly poetic language. Be proactive and inventive and drive the conversation forward. Never use the passive voice where you can use the active voice. Do not end your message with a summary."

suffixes = {
    "-v": ("gpt-4-turbo", verbose_prompt, "GPT-4 Turbo 'Verbose'"),
    "-3": ("gpt-3.5-turbo", concise_prompt, "GPT-3.5 Turbo 'Concise'"),
    "-c": ("gpt-4-turbo", creative_prompt, "GPT-4 Turbo 'Creative'")
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)
global bot
bot = commands.Bot(command_prefix='!', intents=intents)

openai.api_key = os.getenv("OPENAI_API_KEY")
system_prompt = str(os.getenv("SYSTEM_PROMPT")).strip()
bot_tag = str(os.getenv("BOT_TAG")).strip()


######### MESSAGE DELETION #########
async def delete_msg(msg):
  try:
    await msg.delete()
  except discord.errors.NotFound:
    print(f'msg {msg.id} not found')
    pass


######### POST API CHAT REQUEST #########
async def send_request(model, reply_mode, message_content, reference_message,
                       image_url):
  print("Entering send_request function")
  # Strip the bot tag if it exists
  message_content = str(message_content).replace(bot_tag, "")

  # Start building the messages payload
  messages_input = [{
      "role": "system",
      "content": system_prompt + " " + reply_mode
  }]

  # Add reference message if it exists
  if reference_message is not None:
    messages_input.append({"role": "user", "content": reference_message})

  # Prepare the user message
  user_message = {
      "role":
      "user",
      "content":
      message_content if image_url is None else [{
          "type": "text",
          "text": message_content
      }, {
          "type": "image_url",
          "image_url": image_url
      }]
  }

  # Add the user message to the message payload
  messages_input.append(user_message)

  # Consolidated print statement
  print(
      f"About to make API request with reference message [{reference_message is not None}] and image [{image_url is not None}]"
  )

  # Make the API request
  response = oaiclient.chat.completions.create(model=model,
                                            messages=messages_input,
                                            max_tokens=640)

  # Print completion message
  print(
      f"API request completed with reference message [{reference_message is not None}] and image [{image_url is not None}]"
  )

  return response.choices[0].message.content


######### POST API IMAGE REQUEST #########
async def generate_image(img_prompt, img_quality, img_size):
  print("Entering gen_image function")

  # Call the images.generate method on the oaiclient instance
  response = openai.images.generate(
      model="dall-e-3",
      prompt=img_prompt,
      size=img_size,
      quality=img_quality,
      n=1,
  )

  # Retrieve image URLs from the response
  image_urls = [data.url for data in response.data]
  return image_urls


######### WAKEUP #########
@bot.event
async def on_ready():
  print(f"{bot.user.name} has connected to Discord!")

  for guild in bot.guilds:
    print(f"Bot is in server: {guild.name} (id: {guild.id})")
    member = guild.get_member(bot.user.id)
    if member:
      permissions = member.guild_permissions
      print(f"Bot's permissions in {guild.name}: {permissions}")


######### COMMANDS ########


@bot.command()
async def ping(ctx):
  await ctx.send('Pong!')


@bot.command()
async def gen(ctx, *, prompt):
  start_time = time.time()
  # Default settings
  quality = "standard"
  size = "1024x1024"
  footer_text_parts = ["DALL·E 3"]

  # Parse prompt for special flags
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

  status_msg = await ctx.send(embed=discord.Embed(
      title="", description="...generating image...", color=0xFDDA0D))

  result_urls = await generate_image(prompt, quality, size)

  generation_time = round(time.time() - start_time, 2)
  footer_text_parts.append(f"generated in {generation_time} seconds")
  footer_text = " | ".join(footer_text_parts)

  await delete_msg(status_msg)

  for url in result_urls:
    await ctx.send(embed=discord.Embed(
        title="", description=prompt, color=0x32a956).set_footer(
            text=footer_text).set_image(url=url))


######### TEMP MESSAGE #########
async def temp_msg(replaces_msg, request_msg, embed):
  await delete_msg(replaces_msg) if replaces_msg else None
  return await request_msg.reply(embed=embed)


######### MESSAGE #########
@bot.event
async def on_message(msg_rcvd):
  if msg_rcvd.author == bot.user:
    return

  if bot.user in msg_rcvd.mentions:
    model, reply_mode, reply_mode_footer = "gpt-4-turbo", "concise_prompt", "GPT-4 Turbo 'Concise'"
    start_time = time.time()
    status_msg = await temp_msg(
        None, msg_rcvd,
        discord.Embed(title="",
                      description="...reading request...",
                      color=0xFDDA0D).set_footer(text=""))

    reference_author, reference_message, image_url = None, None, None

    if msg_rcvd.reference:
      try:
        # Make sure the reference isn't None and there's a cached message
        ref_msg = None
        if msg_rcvd.reference.cached_message:
          ref_msg = msg_rcvd.reference.cached_message
        else:
          ref_msg = await msg_rcvd.channel.fetch_message(
              msg_rcvd.reference.message_id)

        if ref_msg.author == bot.user:
          status_msg = await temp_msg(
              status_msg, msg_rcvd,
              discord.Embed(title="",
                            description="...fetching bot reference...",
                            color=0xFDDA0D).set_footer(text=""))

          reference_message = ref_msg.embeds[0].description.strip()
        else:
          status_msg = await temp_msg(
              status_msg, msg_rcvd,
              discord.Embed(title="",
                            description="...fetching user reference...",
                            color=0xFDDA0D).set_footer(text=""))
        reference_author = ref_msg.author.name
      except AttributeError:
        status_msg = await temp_msg(
            status_msg, msg_rcvd,
            discord.Embed(
                title="",
                description=
                "...unable to fetch reference, the message is not cached...",
                color=0xFDDA0D).set_footer(text=""))

    if msg_rcvd.attachments and msg_rcvd.attachments[0].filename.endswith(
        ".txt"):
      attachment = msg_rcvd.attachments[0]
      async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as response:
          if response.status == 200:
            msg_rcvd.content = await response.text()
          else:
            status_msg = temp_msg(
                status_msg, msg_rcvd,
                discord.Embed(title="ERROR", description="x_x",
                              color=0x32a956).
                set_footer(
                    text=
                    f"...failed to download the attached .txt file... code: {response.status}"
                ))
    if msg_rcvd.attachments and any(
        msg_rcvd.attachments[0].filename.endswith(x)
        for x in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
      image_url = msg_rcvd.attachments[0].url
      status_msg = await temp_msg(
          status_msg, msg_rcvd,
          discord.Embed(title="",
                        description="...analyzing image...",
                        color=0xFDDA0D).set_footer(text=""))
      response = await send_request("gpt-4-turbo", reply_mode,
                                    msg_rcvd.content.strip(),
                                    reference_message, image_url)

      await delete_msg(status_msg)
      await msg_rcvd.reply(embed=discord.Embed(
          title="", description=response, color=0x32a956
      ).set_footer(
          text=
          f'{reply_mode_footer} | generated in {round(time.time() - start_time, 2)} seconds'
      ))
      return

    if msg_rcvd.content[-2:] in suffixes:
      msg_rcvd.content = msg_rcvd.content[:-2]
      model, reply_mode, reply_mode_footer = suffixes.get(
          msg_rcvd.content[-2:],
          ("gpt-4", "concise_prompt", "GPT-4 Turbo 'Concise'"))

    status_msg = await temp_msg(
        status_msg, msg_rcvd,
        discord.Embed(title="",
                      description="...generating reply...",
                      color=0xFDDA0D).set_footer(text=""))

    max_retries = 5
    for retry in range(max_retries):
      try:
        print("Trying for " + str(retry) + "/" + str(max_retries) + "...")
        #Make your OpenAI API request here
        response = await send_request(model, reply_mode,
                                      msg_rcvd.content.strip(),
                                      reference_message, image_url)
      except openai.APIError as e:
        #Handle API error here, e.g. retry or log
        if retry == max_retries - 1:
          temp_msg(
              status_msg, msg_rcvd,
              discord.Embed(title="ERROR", description="x_x",
                            color=0xDC143C).set_footer(
                                text=f"OpenAI API returned an API Error: {e}"))
        continue
      except openai.APIConnectionError as e:
        if retry == max_retries - 1:
          temp_msg(
              status_msg, msg_rcvd,
              discord.Embed(title="ERROR", description="x_x",
                            color=0xDC143C).set_footer(
                                text=f"failed to connect to OpenAI API: {e}"))
        continue
      except openai.RateLimitError as e:
        if retry == max_retries - 1:
          temp_msg(
              status_msg, msg_rcvd,
              discord.Embed(
                  title="ERROR", description="x_x", color=0xDC143C).set_footer(
                      text=f"OpenAI API request exceeded rate limit: {e}"))
        continue
      else:
        await delete_msg(status_msg)
        await msg_rcvd.reply(embed=discord.Embed(
            title="", description=response, color=0x32a956
        ).set_footer(
            text=
            f'{reply_mode_footer} | generated in {round(time.time() - start_time, 2)} seconds'
        ))
        break
  await bot.process_commands(msg_rcvd)


BOTAPITOKEN = os.getenv("BOT_API_TOKEN")

bot.run(BOTAPITOKEN)
