import discord
from typing import List, Optional

def get_embed_total_length(embed: discord.Embed) -> int:
    """
    Compute the total number of characters used in an embed.
    (Counts title + description + footer text + all fields.)
    """
    total = 0
    if embed.title:
        total += len(embed.title)
    if embed.description:
        total += len(embed.description)
    if embed.footer is not None and embed.footer.text:
        total += len(embed.footer.text)
    for field in embed.fields:
        total += len(field.name) + len(field.value)
    return total

def split_embed(embed: discord.Embed) -> List[discord.Embed]:
    """
    Splits the embed's description into chunks so that each embed is under Discord's 6000 character limit.
    Only the description is split. The title is only included in the first part, and the footer only in the last.
    """
    header_len = len(embed.title) if embed.title else 0
    footer_len = len(embed.footer.text) if (embed.footer and embed.footer.text) else 0
    # Allow for some safe margin: here we use 4096 as a safe chunk size provided header/footer lengths.
    safe_chunk_size = min(4096, 6000 - max(header_len, footer_len))
    
    text = embed.description or ""
    if not text:
        return [embed]
    
    # Split the description into safe chunks.
    chunks = [text[i:i+safe_chunk_size] for i in range(0, len(text), safe_chunk_size)]
    new_embeds = []
    for idx, chunk in enumerate(chunks):
        new_embed = discord.Embed(color=embed.color)
        if idx == 0 and embed.title:
            new_embed.title = embed.title
        new_embed.description = chunk
        if idx == len(chunks) - 1 and embed.footer and embed.footer.text:
            new_embed.set_footer(text=embed.footer.text)
        new_embeds.append(new_embed)
    return new_embeds

async def send_embed(destination, embed: discord.Embed, *, reply_to: Optional[discord.Message] = None) -> None:
    """
    Sends an embed to the destination. If a reply_to is provided (a discord.Message),
    then replies to that message. Handles splitting embeds if they exceed Discord's 6000 character limit.
    
    destination: Either a channel (with a .send method) or a context in which to call send.
    reply_to: Optional discord.Message. If provided, the first embed is sent as a reply to this message.
    """
    if get_embed_total_length(embed) > 6000:
        parts = split_embed(embed)
        if reply_to is not None:
            # First part is a reply.
            await reply_to.reply(embed=parts[0])
            # Subsequent parts can be sent to the same channel.
            for part in parts[1:]:
                await reply_to.channel.send(embed=part)
        else:
            # destination is assumed to be a channel with a send() method.
            await destination.send(embed=parts[0])
            for part in parts[1:]:
                await destination.send(embed=part)
    else:
        if reply_to is not None:
            await reply_to.reply(embed=embed)
        else:
            await destination.send(embed=embed)