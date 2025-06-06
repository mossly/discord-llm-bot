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
        self.default_models = self._get_default_models()
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
    
    def _get_default_models(self) -> dict:
        """Get the default model configuration from ai_commands.py"""
        # Import here to avoid circular imports
        from .ai_commands import MODEL_CONFIG
        return MODEL_CONFIG.copy()
    
    def _load_models_config(self) -> dict:
        """Load models configuration from file, or use defaults"""
        try:
            if os.path.exists(self.models_config_file):
                with open(self.models_config_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded models configuration from {self.models_config_file}")
                    return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load models config: {e}, using defaults")
        
        # Use default configuration
        config = {}
        for model_key, model_config in self.default_models.items():
            config[model_key] = {
                **model_config,
                "enabled": True,
                "admin_only": False
            }
        return config
    
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
            if config.get("enabled", True):
                if not config.get("admin_only", False) or is_user_admin:
                    available[model_key] = config
        
        return available
    
    @app_commands.command(name="models", description="[ADMIN] Manage AI models")
    @app_commands.describe(
        action="Action to perform",
        model="Model to manage (for enable/disable/info actions)",
        admin_only="Set if model should be admin-only (for enable action)"
    )
    async def manage_models(
        self, 
        interaction: discord.Interaction, 
        action: Literal["list", "enable", "disable", "info", "reload"],
        model: Optional[str] = None,
        admin_only: Optional[bool] = None
    ):
        """Admin command to manage AI models"""
        if not self.is_admin(interaction.user.id):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if action == "list":
            await self._list_models(interaction)
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
    
    async def _enable_model(self, interaction: discord.Interaction, model_key: str, admin_only: bool):
        """Enable a model"""
        if model_key not in self.default_models:
            available_models = ", ".join(self.default_models.keys())
            await interaction.response.send_message(
                f"❌ Unknown model: {model_key}\nAvailable models: {available_models}", 
                ephemeral=True
            )
            return
        
        # Ensure model exists in config
        if model_key not in self.models_config:
            self.models_config[model_key] = self.default_models[model_key].copy()
        
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