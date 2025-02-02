import discord

def create_status_embed(status_text: str) -> discord.Embed:
    return discord.Embed(title="", description=status_text, color=0xFDDA0D)

async def update_status(status_msg: discord.Message, new_text: str, *, channel: discord.TextChannel = None) -> discord.Message:
    # If there is an existing status message, delete it.
    if status_msg is not None:
        try:
            await status_msg.delete()
        except Exception as e:
            print(f"Failed to delete previous status message: {e}")
        # Use the channel associated with the previous message if none provided.
        if channel is None:
            channel = status_msg.channel
    else:
        if channel is None:
            raise ValueError("Channel must be provided when status_msg is None.")
            
    # Send the new status message.
    new_msg = await channel.send(embed=create_status_embed(new_text))
    return new_msg