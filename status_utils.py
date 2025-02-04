import discord
import logging

logger = logging.getLogger(__name__)

def create_status_embed(status_text: str) -> discord.Embed:
    logger.debug("Creating status embed with text: %s", status_text)
    return discord.Embed(title="", description=status_text, color=0xFDDA0D)

async def update_status(status_msg: discord.Message, new_text: str, *, channel: discord.TextChannel = None) -> discord.Message:
    logger.info("Updating status message to: %s", new_text)
    # If there is an existing status message, delete it.
    if status_msg is not None:
        try:
            await status_msg.delete()
            logger.info("Deleted previous status message (ID: %s)", status_msg.id)
        except Exception as e:
            logger.exception("Failed to delete previous status message (ID: %s): %s", status_msg.id, e)
        # Use the channel associated with the previous message if none provided.
        if channel is None:
            channel = status_msg.channel
    else:
        if channel is None:
            raise ValueError("Channel must be provided when status_msg is None.")
            
    # Send the new status message.
    new_msg = await channel.send(embed=create_status_embed(new_text))
    logger.info("Sent new status message (ID: %s)", new_msg.id)
    return new_msg