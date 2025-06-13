import discord
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def create_error_embed(error_message: str) -> discord.Embed:
    """Create a standardized error embed with consistent formatting"""
    embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
    embed.set_footer(text=f"Error: {error_message}")
    return embed


def create_success_embed(message: str, title: str = "") -> discord.Embed:
    """Create a standardized success embed with consistent formatting"""
    embed = discord.Embed(title=title, description=message, color=0x32a956)
    return embed

def get_embed_total_length(embed: discord.Embed) -> int:
    logger.debug("Calculating total length of embed.")
    total = 0
    if embed.title:
        total += len(embed.title)
        logger.debug("Title length: %d", len(embed.title))
    if embed.description:
        total += len(embed.description)
        logger.debug("Description length: %d", len(embed.description))
    if embed.footer is not None and embed.footer.text:
        total += len(embed.footer.text)
        logger.debug("Footer text length: %d", len(embed.footer.text))
    for field in embed.fields:
        field_length = len(field.name) + len(field.value)
        total += field_length
        logger.debug("Field '%s' length: %d", field.name, field_length)
    logger.debug("Total embed length: %d", total)
    return total

def split_embed(embed: discord.Embed) -> List[discord.Embed]:
    logger.debug("Splitting embed into chunks if needed.")
    header_len = len(embed.title) if embed.title else 0
    footer_len = len(embed.footer.text) if (embed.footer and embed.footer.text) else 0
    safe_chunk_size = min(4000, 4096 - max(header_len, footer_len))
    logger.debug("Header length: %d, Footer length: %d, Safe chunk size: %d", header_len, footer_len, safe_chunk_size)
    
    text = embed.description or ""
    if not text:
        logger.debug("No description found; returning the original embed.")
        return [embed]
    
    chunks = [text[i:i+safe_chunk_size] for i in range(0, len(text), safe_chunk_size)]
    logger.debug("Description split into %d chunk(s).", len(chunks))
    new_embeds = []
    for idx, chunk in enumerate(chunks):
        new_embed = discord.Embed(color=embed.color)
        if idx == 0 and embed.title:
            new_embed.title = embed.title
            logger.debug("Added title to first embed: %s", embed.title)
        new_embed.description = chunk
        if idx == len(chunks) - 1 and embed.footer and embed.footer.text:
            new_embed.set_footer(text=embed.footer.text)
            logger.debug("Added footer to last embed: %s", embed.footer.text)
        new_embeds.append(new_embed)
    return new_embeds

async def send_embed(destination, embed: discord.Embed, *, reply_to: Optional[discord.Message] = None, interaction: Optional[discord.Interaction] = None, content: Optional[str] = None) -> Optional[discord.Message]:
    total_length = get_embed_total_length(embed)
    logger.debug("Embed total length: %d", total_length)
    if total_length > 4096:
        logger.info("Embed exceeds 4096 characters. Splitting embed into multiple parts.")
        parts = split_embed(embed)
        first_message = None
        if reply_to is not None:
            logger.debug("Sending first embed part as a reply.")
            first_message = await reply_to.reply(content=content, embed=parts[0])
            for part in parts[1:]:
                logger.debug("Sending subsequent embed part to channel: %s", reply_to.channel)
                await reply_to.channel.send(embed=part)
        elif interaction is not None:
            logger.debug("Sending first embed part via interaction followup.")
            first_message = await interaction.followup.send(content=content, embed=parts[0])
            for part in parts[1:]:
                await interaction.followup.send(embed=part)
        else:
            logger.debug("Sending embed parts to destination channel.")
            first_message = await destination.send(content=content, embed=parts[0])
            for part in parts[1:]:
                await destination.send(embed=part)
        logger.info("Embed split into %d parts and sent successfully.", len(parts))
        return first_message
    else:
        logger.debug("Embed within character limit; sending as a single embed.")
        if reply_to is not None:
            message = await reply_to.reply(content=content, embed=embed)
            logger.info("Embed sent as a reply.")
            return message
        elif interaction is not None:
            message = await interaction.followup.send(content=content, embed=embed)
            logger.info("Embed sent via interaction followup.")
            return message
        else:
            message = await destination.send(content=content, embed=embed)
            logger.info("Embed sent to destination.")
            return message


# Export functions for easy importing
__all__ = ['create_error_embed', 'create_success_embed', 'get_embed_total_length', 'split_embed', 'send_embed']