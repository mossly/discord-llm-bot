import logging
import discord
from discord.ext import commands
from generic_chat import prepare_chat_parameters, perform_chat_query
from embed_utils import send_embed  # Add this import

logger = logging.getLogger(__name__)

class ChatCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="chat")
    async def chat(self, ctx: commands.Context, *, prompt: str):
        """
        Text command for chatting.
        Usage: !chat <your message>
        Optionally attaches text files for prompt content or images.
        """
        # Process attachments and (if applicable) reference messages.
        final_prompt, image_url, model, reply_mode, reply_footer, reference_message = await prepare_chat_parameters(prompt, ctx.message.attachments, ctx, is_slash=False)
        duck_cog = self.bot.get_cog("DuckDuckGo")
        try:
            result, elapsed, final_footer = await perform_chat_query(
                prompt=final_prompt,
                api_cog=self.bot.get_cog("APIUtils"),
                channel=ctx.channel,
                duck_cog=duck_cog,
                image_url=image_url,
                reference_message=reference_message,
                model=model,
                reply_mode=reply_mode,
                reply_footer=reply_footer
            )
        except Exception as e:
            error_embed = discord.Embed(title="ERROR", description="x_x", color=0xDC143C)
            error_embed.set_footer(text=f"Error generating reply: {e}")
            return await ctx.reply(embed=error_embed)
        
        embed = discord.Embed(title="", description=result, color=0x32a956)
        embed.set_footer(text=f"{final_footer} | generated in {elapsed} seconds")
        # Use send_embed instead of direct ctx.reply
        await send_embed(ctx.channel, embed, reply_to=ctx.message)