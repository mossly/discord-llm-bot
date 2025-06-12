import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from conversation_history import ConversationHistoryManager

logger = logging.getLogger(__name__)

class ConversationSearch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.history_manager = ConversationHistoryManager()
        
    @app_commands.command(name="stats", description="View your conversation statistics")
    async def stats(self, interaction: discord.Interaction):
        """Show user's conversation statistics"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        
        try:
            stats = self.history_manager.get_user_stats(user_id)
            
            if stats["total_conversations"] == 0:
                await interaction.followup.send(
                    "You don't have any conversation history yet.",
                    ephemeral=True
                )
                return
                
            embed = discord.Embed(
                title="Your Conversation Statistics",
                color=0x00CED1
            )
            
            embed.add_field(
                name="Total Conversations",
                value=stats["total_conversations"],
                inline=True
            )
            
            embed.add_field(
                name="Total Tokens",
                value=f"{stats['total_tokens']:,}",
                inline=True
            )
            
            embed.add_field(
                name="Total Cost",
                value=f"${stats['total_cost']:.4f}",
                inline=True
            )
            
            # Format timestamps
            if stats["first_conversation"]:
                first_time = datetime.fromisoformat(stats["first_conversation"])
                embed.add_field(
                    name="First Conversation",
                    value=first_time.strftime("%Y-%m-%d %H:%M UTC"),
                    inline=True
                )
                
            if stats["last_conversation"]:
                last_time = datetime.fromisoformat(stats["last_conversation"])
                embed.add_field(
                    name="Last Conversation",
                    value=last_time.strftime("%Y-%m-%d %H:%M UTC"),
                    inline=True
                )
                
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting conversation stats: {e}")
            await interaction.followup.send(
                "An error occurred while getting your conversation statistics.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(ConversationSearch(bot))