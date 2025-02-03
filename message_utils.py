import discord
from typing import List, Optional

async def delete_msg(msg):
    try:
        await msg.delete()
    except discord.errors.NotFound:
        print(f"Message {msg.id} not found.")
        pass