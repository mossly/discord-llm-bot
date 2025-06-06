import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import logging
from user_quotas import quota_manager

logger = logging.getLogger(__name__)

class QuotaManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load admin IDs from environment variable and file
        self.admin_ids = self._load_admin_ids()
    
    def _load_admin_ids(self) -> set:
        """Load admin IDs from environment variable or file"""
        import os
        admin_ids = set()
        
        # Try environment variable first (comma-separated list)
        env_admins = os.getenv('BOT_ADMIN_IDS', '')
        if env_admins:
            try:
                admin_ids.update(int(uid.strip()) for uid in env_admins.split(',') if uid.strip())
                logger.info(f"Loaded {len(admin_ids)} admin users from BOT_ADMIN_IDS environment variable")
            except ValueError:
                logger.warning("Invalid admin IDs in BOT_ADMIN_IDS environment variable")
        
        # Try loading from admin_ids.txt file
        try:
            if os.path.exists('admin_ids.txt'):
                with open('admin_ids.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            try:
                                admin_ids.add(int(line))
                            except ValueError:
                                logger.warning(f"Invalid admin ID in admin_ids.txt: {line}")
                logger.info(f"Loaded additional admin users from admin_ids.txt")
        except IOError:
            logger.warning("Could not read admin_ids.txt file")
        
        if admin_ids:
            logger.info(f"Total admin users configured: {len(admin_ids)}")
        else:
            logger.warning("No admin users configured! Set BOT_ADMIN_IDS environment variable or create admin_ids.txt")
        
        return admin_ids
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.admin_ids
    
    @app_commands.command(name="quota", description="Check your current usage quota")
    async def check_quota(self, interaction: discord.Interaction):
        """Allow users to check their own quota"""
        user_id = str(interaction.user.id)
        stats = quota_manager.get_user_stats(user_id)
        
        if stats['is_unlimited']:
            embed = discord.Embed(
                title="📊 Your Usage Quota",
                description="**Unlimited Quota** ♾️",
                color=0x32a956
            )
        else:
            quota = stats['monthly_quota']
            usage = stats['current_usage']
            remaining = stats['remaining_quota']
            percentage_used = (usage / quota * 100) if quota > 0 else 0
            
            # Choose color based on usage percentage
            if percentage_used >= 90:
                color = 0xDC143C  # Red
            elif percentage_used >= 70:
                color = 0xFF8C00  # Orange
            else:
                color = 0x32a956  # Green
                
            embed = discord.Embed(
                title="📊 Your Usage Quota",
                color=color
            )
            embed.add_field(
                name="Monthly Quota",
                value=f"${quota:.2f}",
                inline=True
            )
            embed.add_field(
                name="Used This Month",
                value=f"${usage:.4f}",
                inline=True
            )
            embed.add_field(
                name="Remaining",
                value=f"${remaining:.4f}",
                inline=True
            )
            embed.add_field(
                name="Usage",
                value=f"{percentage_used:.1f}%",
                inline=False
            )
        
        embed.set_footer(text=f"Month: {stats['current_month']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="set-quota", description="[ADMIN] Set a user's monthly quota")
    @app_commands.describe(
        user="The user to set quota for",
        amount="Monthly quota amount in USD"
    )
    async def set_quota(self, interaction: discord.Interaction, user: discord.User, amount: float):
        """Admin command to set user quotas"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if amount < 0:
            await interaction.response.send_message("❌ Quota amount must be non-negative.", ephemeral=True)
            return
        
        user_id = str(user.id)
        quota_manager.set_user_quota(user_id, amount)
        
        embed = discord.Embed(
            title="✅ Quota Updated",
            description=f"Set monthly quota for {user.mention} to ${amount:.2f}",
            color=0x32a956
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="reset-usage", description="[ADMIN] Reset a user's usage for current month")
    @app_commands.describe(
        user="The user to reset usage for"
    )
    async def reset_usage(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to reset user usage"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        user_id = str(user.id)
        quota_manager.reset_user_usage(user_id)
        
        embed = discord.Embed(
            title="✅ Usage Reset",
            description=f"Reset usage for {user.mention} for current month",
            color=0x32a956
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="quota-stats", description="[ADMIN] View quota statistics for all users")
    async def quota_stats(self, interaction: discord.Interaction):
        """Admin command to view all user quota statistics"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        all_stats = quota_manager.get_all_users_stats()
        
        if not all_stats:
            await interaction.response.send_message("No users found in quota system.", ephemeral=True)
            return
        
        # Sort users by usage (highest first)
        sorted_users = sorted(all_stats.items(), key=lambda x: x[1]['current_usage'], reverse=True)
        
        embed = discord.Embed(
            title="📊 All Users Quota Statistics",
            color=0x32a956
        )
        
        description_lines = []
        for user_id, stats in sorted_users[:10]:  # Show top 10 users
            try:
                user = await self.bot.fetch_user(int(user_id))
                username = user.name
            except:
                username = f"User {user_id}"
            
            if stats['is_unlimited']:
                usage_str = f"♾️ Unlimited"
            else:
                quota = stats['monthly_quota']
                usage = stats['current_usage']
                percentage = (usage / quota * 100) if quota > 0 else 0
                usage_str = f"${usage:.3f}/${quota:.2f} ({percentage:.1f}%)"
            
            description_lines.append(f"**{username}**: {usage_str}")
        
        if len(sorted_users) > 10:
            description_lines.append(f"... and {len(sorted_users) - 10} more users")
        
        embed.description = "\n".join(description_lines)
        embed.set_footer(text=f"Total users: {len(all_stats)} | Month: {list(all_stats.values())[0]['current_month']}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="user-quota", description="[ADMIN] Check specific user's quota details")
    @app_commands.describe(
        user="The user to check quota for"
    )
    async def user_quota(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to check specific user's quota"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        user_id = str(user.id)
        stats = quota_manager.get_user_stats(user_id)
        
        embed = discord.Embed(
            title=f"📊 Quota Details for {user.name}",
            color=0x32a956
        )
        
        if stats['is_unlimited']:
            embed.add_field(
                name="Quota Type",
                value="♾️ Unlimited",
                inline=False
            )
        else:
            quota = stats['monthly_quota']
            usage = stats['current_usage']
            remaining = stats['remaining_quota']
            percentage_used = (usage / quota * 100) if quota > 0 else 0
            
            embed.add_field(name="Monthly Quota", value=f"${quota:.2f}", inline=True)
            embed.add_field(name="Used This Month", value=f"${usage:.4f}", inline=True)
            embed.add_field(name="Remaining", value=f"${remaining:.4f}", inline=True)
            embed.add_field(name="Usage Percentage", value=f"{percentage_used:.1f}%", inline=True)
        
        embed.add_field(name="User ID", value=user_id, inline=True)
        embed.add_field(name="Current Month", value=stats['current_month'], inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(QuotaManagement(bot))