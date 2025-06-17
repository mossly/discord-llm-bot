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
from collections import defaultdict
from utils.timezone_manager import timezone_manager

logger = logging.getLogger(__name__)


class ContinentDropdown(discord.ui.Select):
    """First dropdown for selecting continent/region"""
    
    def __init__(self):
        # Group timezones by continent/region
        all_timezones = sorted(pytz.all_timezones)
        continents = set()
        
        for tz in all_timezones:
            if '/' in tz:
                continent = tz.split('/')[0]
                continents.add(continent)
            else:
                # Handle special cases like UTC, GMT, etc.
                if tz in ['UTC', 'GMT', 'Universal']:
                    continents.add('UTC')
        
        continent_options = []
        for continent in sorted(continents):
            emoji_map = {
                'Africa': '🌍',
                'America': '🌎', 
                'Antarctica': '🐧',
                'Arctic': '🧊',
                'Asia': '🌏',
                'Atlantic': '🌊',
                'Australia': '🇦🇺',
                'Europe': '🇪🇺',
                'Indian': '🏝️',
                'Pacific': '🏖️',
                'UTC': '🌍',
                'US': '🇺🇸'
            }
            
            continent_options.append(
                discord.SelectOption(
                    label=continent,
                    value=continent,
                    emoji=emoji_map.get(continent, '🌐')
                )
            )
        
        super().__init__(
            placeholder="1️⃣ First, select a continent/region...",
            options=continent_options[:25],  # Discord limit
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_continent = self.values[0]
        
        # Create timezone dropdown for selected continent
        timezone_dropdown = TimezoneDropdown(selected_continent)
        view = TimezoneSelectionView()
        view.clear_items()
        view.add_item(ContinentDropdown())  # Keep continent selector
        view.add_item(timezone_dropdown)
        
        embed = discord.Embed(
            title="🌍 Set Your Timezone - Step 2",
            description=f"You selected **{selected_continent}**. Now choose your specific timezone:",
            color=0x0099FF
        )
        
        await interaction.response.edit_message(embed=embed, view=view)


class TimezoneDropdown(discord.ui.Select):
    """Second dropdown for selecting specific timezone within continent"""
    
    def __init__(self, continent: str):
        self.continent = continent
        
        # Get all timezones for the selected continent
        all_timezones = sorted(pytz.all_timezones)
        timezone_options = []
        
        if continent == 'UTC':
            # Special handling for UTC and similar
            utc_zones = ['UTC', 'GMT', 'Universal']
            for tz in utc_zones:
                if tz in all_timezones:
                    timezone_options.append(
                        discord.SelectOption(
                            label=tz,
                            value=tz,
                            description="Coordinated Universal Time"
                        )
                    )
        else:
            # Filter timezones by continent
            for tz in all_timezones:
                if tz.startswith(f"{continent}/"):
                    city = tz.split('/', 1)[1].replace('_', ' ')
                    # Show current UTC offset
                    try:
                        tz_obj = pytz.timezone(tz)
                        now = datetime.now(tz_obj)
                        offset = now.strftime('%z')
                        if offset:
                            # Format offset as +/-HH:MM
                            offset_formatted = f"UTC{offset[:3]}:{offset[3:]}"
                        else:
                            offset_formatted = ""
                    except:
                        offset_formatted = ""
                    
                    label = f"{city} {offset_formatted}".strip()
                    timezone_options.append(
                        discord.SelectOption(
                            label=label[:100],  # Discord limit
                            value=tz,
                            description=tz[:100]  # Show full timezone name
                        )
                    )
        
        # Limit to Discord's 25 option maximum
        timezone_options = timezone_options[:25]
        
        super().__init__(
            placeholder=f"2️⃣ Select timezone in {continent}...",
            options=timezone_options,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        timezone = self.values[0]
        success, message = await timezone_manager.set_user_timezone(interaction.user.id, timezone)
        
        if success:
            # Show current time in the selected timezone
            try:
                tz = pytz.timezone(timezone)
                current_time = datetime.now(tz).strftime("%I:%M %p on %A, %B %d")
                
                embed = discord.Embed(
                    title="✅ Timezone Updated Successfully",
                    description=(
                        f"Your timezone has been set to **{timezone}**\n\n"
                        f"🕐 Current time in your timezone: **{current_time}**\n\n"
                        f"This timezone will be used for both reminders and tasks."
                    ),
                    color=0x00FF00
                )
            except Exception as e:
                embed = discord.Embed(
                    title="✅ Timezone Updated",
                    description=f"Your timezone has been set to **{timezone}**",
                    color=0x00FF00
                )
        else:
            embed = discord.Embed(
                title="❌ Error Setting Timezone",
                description=f"Failed to set timezone: {message}",
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


class TimezoneSelectionView(discord.ui.View):
    """View containing the two-step timezone selection process"""
    
    def __init__(self):
        super().__init__(timeout=120)  # Longer timeout for two-step process
        self.add_item(ContinentDropdown())
    
    @discord.ui.button(label="Enter Custom Timezone", style=discord.ButtonStyle.secondary, emoji="⚙️", row=2)
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
            title="🌍 Set Your Timezone - Step 1",
            description=(
                f"Your timezone is currently set to: **{current_tz}**\n\n"
                f"Choose your timezone in two easy steps:\n"
                f"1️⃣ Select your continent/region\n"
                f"2️⃣ Select your specific timezone\n\n"
                f"This setting will be used for both reminders and tasks."
            ),
            color=0x0099FF
        )
        
        await interaction.response.send_message(embed=embed, view=TimezoneSelectionView(), ephemeral=True)
    
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