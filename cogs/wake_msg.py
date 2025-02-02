import discord
from discord.ext import commands

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name} has connected to Discord!")
        for guild in self.bot.guilds:
            print(f"Bot is in server: {guild.name} (id: {guild.id})")
            member = guild.get_member(self.bot.user.id)
            if member:
                print(f"Bot's permissions in {guild.name}: {member.guild_permissions}")

# Asynchronous setup function
async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))