import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional
import logging
import json
import os

logger = logging.getLogger(__name__)

class ModelManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load admin IDs from environment variable and file
        self.admin_ids = self._load_admin_ids()
        # Load model configuration
        self.models_config_file = "models_config.json"
        self.models_config = self._load_models_config()
    
    def _load_admin_ids(self) -> set:
        """Load admin IDs from environment variable or file"""
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
    
    def _load_models_config(self) -> dict:
        """Load models configuration from file"""
        try:
            if os.path.exists(self.models_config_file):
                with open(self.models_config_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded models configuration from {self.models_config_file}")
                    return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load models config: {e}")
        
        # Return empty config if no file exists
        logger.info("No models configuration file found. Starting with empty configuration.")
        return {}
    
    def _save_models_config(self):
        """Save models configuration to file"""
        try:
            with open(self.models_config_file, 'w') as f:
                json.dump(self.models_config, f, indent=2)
                logger.info(f"Saved models configuration to {self.models_config_file}")
        except IOError as e:
            logger.error(f"Could not save models config: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.admin_ids
    
    def get_available_models(self, user_id: int = None) -> dict:
        """Get models available to a user"""
        available = {}
        is_user_admin = user_id and self.is_admin(user_id)
        
        for model_key, config in self.models_config.items():
            # Skip comment fields that are strings instead of dicts
            if not isinstance(config, dict):
                continue
            if config.get("enabled", True):
                if not config.get("admin_only", False) or is_user_admin:
                    available[model_key] = config
        
        return available
    
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
        action: Literal["list", "available", "add", "edit", "remove", "enable", "disable", "info", "reload"],
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
            "color": 0x32a956,  # Default green color
            "default_footer": footer_text,
            "api_model": api_model,
            "supports_images": supports_images,
            "api": api_provider,
            "enabled": True,
            "admin_only": admin_only
        }
        
        # Add to configuration
        self.models_config[model_key] = new_model_config
        self._save_models_config()
        
        # Also update the default models config in ai_commands for runtime use
        from .ai_commands import MODEL_CONFIG
        MODEL_CONFIG[model_key] = {
            "name": display_name,
            "color": 0x32a956,
            "default_footer": footer_text,
            "api_model": api_model,
            "supports_images": supports_images,
            "api": api_provider
        }
        
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
        
        # Save updated configuration
        self.models_config[model_key] = current_config
        self._save_models_config()
        
        # Also update runtime MODEL_CONFIG if it exists
        from .ai_commands import MODEL_CONFIG
        if model_key in MODEL_CONFIG:
            MODEL_CONFIG[model_key].update({
                "name": current_config.get("name"),
                "default_footer": current_config.get("default_footer"),
                "api_model": current_config.get("api_model"),
                "supports_images": current_config.get("supports_images"),
                "api": current_config.get("api")
            })
        
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
        
        # Remove from configuration
        del self.models_config[model_key]
        self._save_models_config()
        
        # Also remove from runtime MODEL_CONFIG if it exists
        from .ai_commands import MODEL_CONFIG
        if model_key in MODEL_CONFIG:
            del MODEL_CONFIG[model_key]
        
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
        
        self.models_config[model_key]["enabled"] = True
        self.models_config[model_key]["admin_only"] = admin_only
        self._save_models_config()
        
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
        
        self.models_config[model_key]["enabled"] = False
        self._save_models_config()
        
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
        self.models_config = self._load_models_config()
        
        embed = discord.Embed(
            title="🔄 Models Reloaded",
            description="Models configuration has been reloaded from file",
            color=0x32a956
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModelManagement(bot))