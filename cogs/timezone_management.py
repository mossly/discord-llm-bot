"""
Centralized timezone management cog
Provides /timezone set and /timezone show commands for both reminders and tasks
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import pytz
from datetime import datetime
from utils.timezone_manager import timezone_manager

logger = logging.getLogger(__name__)


class TimezoneDropdown(discord.ui.Select):
    """Dropdown for selecting timezones"""
    
    def __init__(self):
        # Common timezones
        timezone_options = [
            discord.SelectOption(label="Pacific/Auckland (GMT+13)", value="Pacific/Auckland", description="New Zealand", emoji="🇳🇿"),
            discord.SelectOption(label="Australia/Sydney (GMT+11)", value="Australia/Sydney", description="Australia East", emoji="🇦🇺"),
            discord.SelectOption(label="Asia/Tokyo (GMT+9)", value="Asia/Tokyo", description="Japan", emoji="🇯🇵"),
            discord.SelectOption(label="Asia/Shanghai (GMT+8)", value="Asia/Shanghai", description="China", emoji="🇨🇳"),
            discord.SelectOption(label="Asia/Kolkata (GMT+5:30)", value="Asia/Kolkata", description="India", emoji="🇮🇳"),
            discord.SelectOption(label="Europe/London (GMT+0)", value="Europe/London", description="UK", emoji="🇬🇧"),
            discord.SelectOption(label="Europe/Paris (GMT+1)", value="Europe/Paris", description="France/Germany", emoji="🇫🇷"),
            discord.SelectOption(label="America/New_York (GMT-5)", value="America/New_York", description="US East", emoji="🇺🇸"),
            discord.SelectOption(label="America/Chicago (GMT-6)", value="America/Chicago", description="US Central", emoji="🇺🇸"),
            discord.SelectOption(label="America/Denver (GMT-7)", value="America/Denver", description="US Mountain", emoji="🇺🇸"),
            discord.SelectOption(label="America/Los_Angeles (GMT-8)", value="America/Los_Angeles", description="US West", emoji="🇺🇸"),
            discord.SelectOption(label="UTC (GMT+0)", value="UTC", description="Coordinated Universal Time", emoji="🌍"),
        ]
        
        super().__init__(
            placeholder="Select your timezone...",
            options=timezone_options,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        timezone = self.values[0]
        success, message = await timezone_manager.set_user_timezone(interaction.user.id, timezone)
        
        if success:
            # Show current time in the selected timezone
            tz = pytz.timezone(timezone)
            current_time = datetime.now(tz).strftime("%I:%M %p on %A, %B %d")
            
            embed = discord.Embed(
                title="✅ Timezone Updated",
                description=(
                    f"Your timezone has been set to **{timezone}**\n"
                    f"Current time in your timezone: **{current_time}**"
                ),
                color=0x00FF00
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=message,
                color=0xFF0000
            )
        
        await interaction.response.edit_message(embed=embed, view=None)


class CustomTimezoneModal(discord.ui.Modal):
    """Modal for entering custom timezone"""
    
    def __init__(self):
        super().__init__(title="Set Custom Timezone")
    
    timezone_input = discord.ui.TextInput(
        label="Timezone",
        placeholder="e.g., America/Phoenix, Europe/Rome, Asia/Seoul",
        style=discord.TextStyle.short,
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        timezone = self.timezone_input.value.strip()
        success, message = await timezone_manager.set_user_timezone(interaction.user.id, timezone)
        
        if success:
            try:
                tz = pytz.timezone(timezone)
                current_time = datetime.now(tz).strftime("%I:%M %p on %A, %B %d")
                
                embed = discord.Embed(
                    title="✅ Timezone Updated",
                    description=(
                        f"Your timezone has been set to **{timezone}**\n"
                        f"Current time in your timezone: **{current_time}**"
                    ),
                    color=0x00FF00
                )
            except pytz.exceptions.UnknownTimeZoneError:
                embed = discord.Embed(
                    title="✅ Timezone Updated",
                    description=f"Your timezone has been set to **{timezone}**",
                    color=0x00FF00
                )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to set timezone: {message}",
                color=0xFF0000
            )
        
        await interaction.response.edit_message(embed=embed, view=None)


class TimezoneView(discord.ui.View):
    """View containing timezone dropdown and custom button"""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TimezoneDropdown())
    
    @discord.ui.button(label="Custom Timezone", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def custom_timezone(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CustomTimezoneModal()
        await interaction.response.send_modal(modal)


class TimezoneManagement(commands.Cog):
    """Cog for centralized timezone management"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    timezone = app_commands.Group(name="timezone", description="Manage your timezone settings")
    
    @timezone.command(name="set", description="Set your timezone preferences for reminders and tasks")
    async def set_timezone(self, interaction: discord.Interaction):
        """Set your timezone preferences using a dropdown menu"""
        logger.info(f"User {interaction.user.id} is setting their timezone")
        
        current_tz = await timezone_manager.get_user_timezone(interaction.user.id)
        
        embed = discord.Embed(
            title="🌍 Set Your Timezone",
            description=(
                f"Your timezone is currently set to: **{current_tz}**\n\n"
                f"Please select your timezone from the dropdown menu below, or use the 'Custom Timezone' button if yours is not listed.\n\n"
                f"This setting will be used for both reminders and tasks."
            ),
            color=0x0099FF
        )
        
        await interaction.response.send_message(embed=embed, view=TimezoneView(), ephemeral=True)
    
    @timezone.command(name="show", description="Show your current timezone setting")
    async def show_timezone(self, interaction: discord.Interaction):
        """Show the user's current timezone setting"""
        logger.info(f"User {interaction.user.id} checking their timezone")
        
        try:
            user_timezone = await timezone_manager.get_user_timezone(interaction.user.id)
            
            # Format the current time in the user's timezone
            local_tz = pytz.timezone(user_timezone)
            current_time = datetime.now(local_tz)
            local_time = current_time.strftime("%I:%M %p on %A, %B %d, %Y")
            
            embed = discord.Embed(
                title="🌍 Your Timezone",
                description=(
                    f"Your timezone is currently set to: **{user_timezone}**\n\n"
                    f"Current time in your timezone: **{local_time}**\n\n"
                    f"You can change this with `/timezone set`"
                ),
                color=0x0099FF
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error showing timezone: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while processing your timezone. Your current setting is: {user_timezone}",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TimezoneManagement(bot))