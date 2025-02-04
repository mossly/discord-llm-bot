import discord
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

async def delete_msg(msg):
    try:
        await msg.delete()
        logger.info("Deleted message with ID %s", msg.id)
    except discord.errors.NotFound:
        logger.warning("Message with ID %s not found.", msg.id)