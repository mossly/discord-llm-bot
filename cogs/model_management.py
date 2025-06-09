import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional
import logging
import json
import os
from .model_cache import get_model_cache, initialize_model_cache

logger = logging.getLogger(__name__)

class ModelManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize the high-performance model cache
        self.cache = initialize_model_cache()
        logger.info("ModelManagement initialized with high-performance caching")
    
    @property
    def models_config(self) -> dict:
        """Get models configuration from cache"""
        return self.cache._models_config
    
    def _save_models_config(self):
        """Save models configuration (handled by cache)"""
        # This is now handled automatically by the cache
        pass
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin (cached)"""
        return self.cache.is_admin(user_id)
    
    def get_available_models(self, user_id: int = None) -> dict:
        """Get models available to a user (highly optimized with cache)"""
        return self.cache.get_available_models(user_id)
    
    def get_model_config(self, model_key: str) -> dict:
        """Get configuration for a specific model (cached)"""
        return self.cache.get_model_config(model_key)
    
    @app_commands.command(name="models", description="Manage AI models (admin) or list available models (users)")
    @app_commands.describe(
        action="Action to perform",
        model="Model key to manage",
        admin_only="Set if model should be admin-only (for enable/add/edit actions)",
        display_name="Display name for the model (for add/edit actions)",
        api_model="API model identifier (for add/edit actions)",
        api_provider="API provider: openai or openrouter (for add/edit actions)",
        supports_images="Whether model supports images (for add/edit actions)",
        footer_text="Footer text to display (for add/edit actions)"
    )
    async def manage_models(
        self, 
        interaction: discord.Interaction, 
        action: Literal["list", "available", "add", "edit", "remove", "enable", "disable", "info", "reload", "reset-to-default"],
        model: Optional[str] = None,
        admin_only: Optional[bool] = None,
        display_name: Optional[str] = None,
        api_model: Optional[str] = None,
        api_provider: Optional[Literal["openai", "openrouter"]] = None,
        supports_images: Optional[bool] = None,
        footer_text: Optional[str] = None
    ):
        """Command to manage AI models (admin) or list available models (users)"""
        # Allow 'available' action for all users, but require admin for other actions
        if action != "available" and not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if action == "list":
            await self._list_models(interaction)
        elif action == "available":
            await self._list_available_models(interaction)
        elif action == "add":
            if not model:
                await interaction.response.send_message("❌ Model key is required for add action.", ephemeral=True)
                return
            await self._add_model(interaction, model, display_name, api_model, api_provider, supports_images, footer_text, admin_only or False)
        elif action == "edit":
            if not model:
                await interaction.response.send_message("❌ Model key is required for edit action.", ephemeral=True)
                return
            await self._edit_model(interaction, model, display_name, api_model, api_provider, supports_images, footer_text, admin_only)
        elif action == "remove":
            if not model:
                await interaction.response.send_message("❌ Model key is required for remove action.", ephemeral=True)
                return
            await self._remove_model(interaction, model)
        elif action == "enable":
            if not model:
                await interaction.response.send_message("❌ Model name is required for enable action.", ephemeral=True)
                return
            await self._enable_model(interaction, model, admin_only or False)
        elif action == "disable":
            if not model:
                await interaction.response.send_message("❌ Model name is required for disable action.", ephemeral=True)
                return
            await self._disable_model(interaction, model)
        elif action == "info":
            if not model:
                await interaction.response.send_message("❌ Model name is required for info action.", ephemeral=True)
                return
            await self._model_info(interaction, model)
        elif action == "reload":
            await self._reload_models(interaction)
        elif action == "reset-to-default":
            await self._reset_to_default(interaction)
    
    async def _list_models(self, interaction: discord.Interaction):
        """List all models with their status"""
        embed = discord.Embed(
            title="🤖 AI Models Management",
            color=0x32a956
        )
        
        enabled_models = []
        disabled_models = []
        
        for model_key, config in self.models_config.items():
            # Skip comment fields that are strings instead of dicts
            if not isinstance(config, dict):
                continue
            status_emoji = "✅" if config.get("enabled", True) else "❌"
            admin_emoji = "🔒" if config.get("admin_only", False) else "🔓"
            model_name = config.get("name", model_key)
            
            model_line = f"{status_emoji} {admin_emoji} **{model_key}** - {model_name}"
            
            if config.get("enabled", True):
                enabled_models.append(model_line)
            else:
                disabled_models.append(model_line)
        
        if enabled_models:
            embed.add_field(
                name="Enabled Models",
                value="\n".join(enabled_models),
                inline=False
            )
        
        if disabled_models:
            embed.add_field(
                name="Disabled Models", 
                value="\n".join(disabled_models),
                inline=False
            )
        
        embed.set_footer(text="✅ = Enabled | ❌ = Disabled | 🔓 = Public | 🔒 = Admin Only")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _list_available_models(self, interaction: discord.Interaction):
        """List models available to the user"""
        available_models = self.get_available_models(interaction.user.id)
        
        if not available_models:
            embed = discord.Embed(
                title="No Models Available",
                description="No AI models are currently available to you.",
                color=0xDC143C
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🤖 Available AI Models",
            color=0x32a956
        )
        
        model_lines = []
        for model_key, config in available_models.items():
            name = config.get("name", model_key)
            supports_images = "🖼️" if config.get("supports_images", False) else ""
            model_lines.append(f"**{model_key}** - {name} {supports_images}")
        
        embed.description = "\n".join(model_lines)
        embed.set_footer(text="Use these model names with the /chat command | 🖼️ = Supports images")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _add_model(self, interaction: discord.Interaction, model_key: str, display_name: str, api_model: str, api_provider: str, supports_images: bool, footer_text: str, admin_only: bool):
        """Add a new model configuration"""
        # Validate required parameters
        if not api_model:
            await interaction.response.send_message("❌ API model identifier is required for add action.", ephemeral=True)
            return
        
        if not api_provider:
            await interaction.response.send_message("❌ API provider (openai/openrouter) is required for add action.", ephemeral=True)
            return
        
        # Check if model already exists
        if model_key in self.models_config:
            await interaction.response.send_message(f"❌ Model '{model_key}' already exists. Use 'enable' or 'info' to manage it.", ephemeral=True)
            return
        
        # Set defaults for optional parameters
        display_name = display_name or model_key
        footer_text = footer_text or model_key
        supports_images = supports_images or False
        
        # Create new model configuration
        new_model_config = {
            "name": display_name,
            "default_footer": footer_text,
            "api_model": api_model,
            "supports_images": supports_images,
            "supports_tools": True,  # Default to supporting tools
            "api": api_provider,
            "enabled": True,
            "admin_only": admin_only
        }
        
        # Add to cache (automatically saves to file)
        self.cache.update_model_config(model_key, new_model_config)
        
        access_text = "admin-only" if admin_only else "public"
        embed = discord.Embed(
            title="✅ Model Added",
            description=f"New model **{model_key}** has been added and enabled ({access_text})",
            color=0x32a956
        )
        embed.add_field(name="Display Name", value=display_name, inline=True)
        embed.add_field(name="API Model", value=api_model, inline=True)
        embed.add_field(name="API Provider", value=api_provider, inline=True)
        embed.add_field(name="Supports Images", value="✅ Yes" if supports_images else "❌ No", inline=True)
        embed.add_field(name="Footer", value=footer_text, inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _edit_model(self, interaction: discord.Interaction, model_key: str, display_name: str, api_model: str, api_provider: str, supports_images: bool, footer_text: str, admin_only: bool):
        """Edit an existing model configuration"""
        # Check if model exists
        if model_key not in self.models_config:
            await interaction.response.send_message(f"❌ Model '{model_key}' not found. Use 'add' to create it first.", ephemeral=True)
            return
        
        # Get current configuration
        current_config = self.models_config[model_key].copy()
        changes_made = []
        
        # Update only provided parameters
        if display_name is not None:
            current_config["name"] = display_name
            changes_made.append(f"Display name: {display_name}")
        
        if api_model is not None:
            current_config["api_model"] = api_model
            changes_made.append(f"API model: {api_model}")
        
        if api_provider is not None:
            current_config["api"] = api_provider
            changes_made.append(f"API provider: {api_provider}")
        
        if supports_images is not None:
            current_config["supports_images"] = supports_images
            changes_made.append(f"Image support: {'Yes' if supports_images else 'No'}")
        
        if footer_text is not None:
            current_config["default_footer"] = footer_text
            changes_made.append(f"Footer: {footer_text}")
        
        if admin_only is not None:
            current_config["admin_only"] = admin_only
            changes_made.append(f"Access: {'Admin-only' if admin_only else 'Public'}")
        
        if not changes_made:
            await interaction.response.send_message("❌ No changes specified. Provide at least one parameter to edit.", ephemeral=True)
            return
        
        # Save updated configuration to cache
        self.cache.update_model_config(model_key, current_config)
        
        embed = discord.Embed(
            title="✅ Model Updated",
            description=f"Model **{model_key}** has been updated",
            color=0x32a956
        )
        embed.add_field(
            name="Changes Made",
            value="\n".join(f"• {change}" for change in changes_made),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _remove_model(self, interaction: discord.Interaction, model_key: str):
        """Remove a model configuration"""
        # Check if model exists
        if model_key not in self.models_config:
            await interaction.response.send_message(f"❌ Model '{model_key}' not found.", ephemeral=True)
            return
        
        # Get model info for confirmation
        model_config = self.models_config[model_key]
        model_name = model_config.get("name", model_key)
        
        # Remove from cache (automatically saves to file)
        self.cache.remove_model_config(model_key)
        
        embed = discord.Embed(
            title="🗑️ Model Removed",
            description=f"Model **{model_key}** ({model_name}) has been permanently removed",
            color=0xFF6B35  # Orange color for removal
        )
        embed.add_field(
            name="⚠️ Note",
            value="This action cannot be undone. Users will no longer be able to access this model.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _enable_model(self, interaction: discord.Interaction, model_key: str, admin_only: bool):
        """Enable a model"""
        # Check if model exists in current config
        if model_key not in self.models_config:
            available_models = ", ".join(self.models_config.keys())
            await interaction.response.send_message(
                f"❌ Unknown model: {model_key}\nAvailable models: {available_models}", 
                ephemeral=True
            )
            return
        
        # Get current config and update it
        current_config = self.cache.get_model_config(model_key)
        if current_config:
            current_config = current_config.copy()
            current_config["enabled"] = True
            current_config["admin_only"] = admin_only
            self.cache.update_model_config(model_key, current_config)
        
        access_text = "admin-only" if admin_only else "public"
        embed = discord.Embed(
            title="✅ Model Enabled",
            description=f"Model **{model_key}** has been enabled ({access_text})",
            color=0x32a956
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _disable_model(self, interaction: discord.Interaction, model_key: str):
        """Disable a model"""
        if model_key not in self.models_config:
            await interaction.response.send_message(f"❌ Model {model_key} not found in configuration.", ephemeral=True)
            return
        
        # Get current config and update it
        current_config = self.cache.get_model_config(model_key)
        if current_config:
            current_config = current_config.copy()
            current_config["enabled"] = False
            self.cache.update_model_config(model_key, current_config)
        
        embed = discord.Embed(
            title="❌ Model Disabled",
            description=f"Model **{model_key}** has been disabled",
            color=0xDC143C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _model_info(self, interaction: discord.Interaction, model_key: str):
        """Show detailed information about a model"""
        if model_key not in self.models_config:
            await interaction.response.send_message(f"❌ Model {model_key} not found.", ephemeral=True)
            return
        
        config = self.models_config[model_key]
        
        embed = discord.Embed(
            title=f"🤖 Model Info: {model_key}",
            color=0x32a956 if config.get("enabled", True) else 0xDC143C
        )
        
        embed.add_field(name="Display Name", value=config.get("name", "N/A"), inline=True)
        embed.add_field(name="API Model", value=config.get("api_model", "N/A"), inline=True)
        embed.add_field(name="API Provider", value=config.get("api", "N/A"), inline=True)
        embed.add_field(name="Status", value="✅ Enabled" if config.get("enabled", True) else "❌ Disabled", inline=True)
        embed.add_field(name="Access", value="🔒 Admin Only" if config.get("admin_only", False) else "🔓 Public", inline=True)
        embed.add_field(name="Image Support", value="✅ Yes" if config.get("supports_images", False) else "❌ No", inline=True)
        embed.add_field(name="Footer Text", value=config.get("default_footer", "N/A"), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _reload_models(self, interaction: discord.Interaction):
        """Reload models configuration from file"""
        self.cache.reload_cache()
        
        embed = discord.Embed(
            title="🔄 Models Reloaded",
            description="Models configuration has been reloaded from file",
            color=0x32a956
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _reset_to_default(self, interaction: discord.Interaction):
        """Reset models configuration to default"""
        # Check if default file exists
        models_config_default_file = "models_config_default.json"
        if not os.path.exists(models_config_default_file):
            await interaction.response.send_message("❌ Default configuration file not found.", ephemeral=True)
            return
        
        try:
            # Copy default to data directory, overwriting existing
            import shutil
            os.makedirs("/data", exist_ok=True)
            models_config_file = "/data/models_config.json"
            shutil.copy2(models_config_default_file, models_config_file)
            logger.info(f"Reset models configuration from {models_config_default_file}")
            
            # Reload the cache
            self.cache.reload_cache()
            
            embed = discord.Embed(
                title="🔄 Models Reset to Default",
                description="Models configuration has been reset to default values. All custom models and settings have been removed.",
                color=0xFF6B35  # Orange to indicate data was reset
            )
            embed.add_field(
                name="⚠️ Note",
                value="This action removed all custom model configurations. Use `/models list` to see the current models.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Failed to reset models configuration: {e}")
            await interaction.response.send_message(f"❌ Failed to reset configuration: {e}", ephemeral=True)
    
    @app_commands.command(name="cache-stats", description="Show model cache performance statistics (admin only)")
    async def cache_stats(self, interaction: discord.Interaction):
        """Show cache performance statistics"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        stats = self.cache.get_cache_stats()
        
        embed = discord.Embed(
            title="📊 Model Cache Statistics",
            color=0x32a956
        )
        
        embed.add_field(name="Models Loaded", value=stats["models_count"], inline=True)
        embed.add_field(name="Admin Users", value=stats["admin_count"], inline=True)
        embed.add_field(name="Cache Version", value=stats["cache_version"], inline=True)
        
        embed.add_field(name="Cache Hits", value=stats["cache_hits"], inline=True)
        embed.add_field(name="Cache Misses", value=stats["cache_misses"], inline=True)
        embed.add_field(name="Hit Rate", value=f"{stats['hit_rate_percent']}%", inline=True)
        
        uptime_hours = stats["uptime_seconds"] / 3600
        embed.add_field(name="Cache Uptime", value=f"{uptime_hours:.2f} hours", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModelManagement(bot))