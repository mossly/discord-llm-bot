import discord

def create_status_embed(status_text: str) -> discord.Embed:
    """
    Create an embed for a status update using a consistent style.
    """
    return discord.Embed(title="", description=status_text, color=0xFDDA0D)

async def update_status(status_msg: discord.Message, new_text: str, *, channel: discord.TextChannel = None) -> discord.Message:
    """
    Update an existing status message with new text.
    If status_msg is None, a new message is sent on the given channel.
    
    Args:
      status_msg (Optional[discord.Message]): The message to update (or None if not yet created).
      new_text (str): The new status text.
      channel (Optional[discord.TextChannel]): Required if status_msg is None.
      
    Returns:
      discord.Message: The updated (or newly-sent) status message.
    """
    if status_msg is None:
        if channel is None:
            raise ValueError("Channel must be provided when status_msg is None.")
        new_msg = await channel.send(embed=create_status_embed(new_text))
        return new_msg
    else:
        try:
            embed = create_status_embed(new_text)
            await status_msg.edit(embed=embed)
            return status_msg
        except Exception as e:
            print(f"Failed to update status message: {e}")
            # Fall back to sending a new message
            if channel is None:
                channel = status_msg.channel
            new_msg = await channel.send(embed=create_status_embed(new_text))
            return new_msg