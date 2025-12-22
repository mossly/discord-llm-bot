"""
Centralized configuration management for Discord LLM bot
Handles environment variable loading and configuration validation
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages all configuration settings for the Discord bot"""

    PROMPTS_DIRECTORY = '/data/prompts'

    def __init__(self):
        self._config = {}
        self._load_configuration()

    def _load_prompt(self, name: str, env_var: str, default: str) -> str:
        """Load prompt from file or environment variable.

        Priority:
        1. File at /data/prompts/{name}.txt (if exists)
        2. Environment variable
        3. Default value
        """
        file_path = f"{self.PROMPTS_DIRECTORY}/{name}.txt"

        # Try file first
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        logger.info(f"Loaded {name} from file: {file_path}")
                        return content
            except Exception as e:
                logger.warning(f"Failed to load {name} from file: {e}")

        # Fall back to environment variable
        env_value = os.getenv(env_var, '')
        if env_value:
            logger.info(f"Loaded {name} from environment variable")
            return env_value

        # Use default
        logger.info(f"Using default {name}")
        return default
    
    def _load_configuration(self):
        """Load all configuration from environment variables"""
        # Core Discord bot settings
        self._config.update({
            'bot_token': self._get_required_env('BOT_API_TOKEN'),
            'bot_tag': os.getenv('BOT_TAG', ''),
            'command_prefix': os.getenv('COMMAND_PREFIX', '!'),
        })
        
        # API Keys
        self._config.update({
            'openai_api_key': self._get_required_env('OPENAI_API_KEY'),
            'openrouter_api_key': self._get_required_env('OPENROUTER_API_KEY'),
        })
        
        # System prompts (file-based with env fallback)
        self._config.update({
            'system_prompt': self._load_prompt(
                'system_prompt',
                'SYSTEM_PROMPT',
                'You are a helpful assistant.'
            ),
            'fun_prompt': self._load_prompt(
                'fun_prompt',
                'FUN_PROMPT',
                'Write an amusing and sarcastic response!'
            ),
        })
        
        # Optional settings
        self._config.update({
            'duck_proxy': os.getenv('DUCK_PROXY'),
            'admin_ids': self._parse_admin_ids(),
            'unlimited_user_ids': self._parse_unlimited_user_ids(),
        })
        
        # Default model configuration
        self._config.update({
            'default_model': os.getenv('DEFAULT_MODEL', 'gemini-3-flash-preview'),
            'max_tokens_default': int(os.getenv('MAX_TOKENS_DEFAULT', '8000')),
        })
        
        # Data paths
        self._config.update({
            'data_directory': '/data',
            'prompts_directory': self.PROMPTS_DIRECTORY,
            'user_quotas_file': '/data/user_quotas.json',
            'conversation_history_file': '/data/conversation_history.json',
            'reminders_file': '/data/reminders.json',
            'user_timezones_file': '/data/user_timezones.json',
            'log_file': '/data/reminders.log',
        })
        
        logger.info("Configuration loaded successfully")
    
    def _get_required_env(self, key: str) -> str:
        """Get a required environment variable or raise an error"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    
    def _parse_admin_ids(self) -> List[str]:
        """Parse admin IDs from environment variable or file"""
        admin_ids = set()
        
        # Try environment variable first
        env_admin_ids = os.getenv('BOT_ADMIN_IDS', '')
        if env_admin_ids:
            try:
                admin_ids.update(uid.strip() for uid in env_admin_ids.split(',') if uid.strip())
                logger.info(f"Loaded {len(admin_ids)} admin IDs from environment")
            except Exception as e:
                logger.error(f"Error parsing admin IDs from environment: {e}")
        
        # Try admin_ids.txt file as fallback
        try:
            admin_file = 'admin_ids.txt'
            if os.path.exists(admin_file):
                with open(admin_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):  # Skip comments
                            admin_ids.add(line)
                logger.info(f"Loaded {len(admin_ids)} admin IDs from file")
        except Exception as e:
            logger.error(f"Error loading admin IDs from file: {e}")
        
        return list(admin_ids)
    
    def _parse_unlimited_user_ids(self) -> List[str]:
        """Parse unlimited quota user IDs from environment variable"""
        unlimited_ids = []
        env_unlimited = os.getenv('BOT_UNLIMITED_USER_IDS', '')
        if env_unlimited:
            try:
                unlimited_ids = [uid.strip() for uid in env_unlimited.split(',') if uid.strip()]
                logger.info(f"Loaded {len(unlimited_ids)} unlimited quota users from environment")
            except Exception as e:
                logger.error(f"Error parsing unlimited user IDs: {e}")
        return unlimited_ids
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self._config.get(key, default)
    
    def get_required(self, key: str) -> Any:
        """Get a required configuration value or raise an error"""
        if key not in self._config:
            raise ValueError(f"Required configuration key '{key}' not found")
        return self._config[key]
    
    def is_admin(self, user_id: str) -> bool:
        """Check if a user ID is an admin"""
        return user_id in self.get('admin_ids', [])
    
    def has_unlimited_quota(self, user_id: str) -> bool:
        """Check if a user has unlimited quota"""
        return user_id in self.get('unlimited_user_ids', [])
    
    def get_system_prompt(self, use_fun: bool = False) -> str:
        """Get the appropriate system prompt.

        Prompts are loaded with priority: file > env var > default.
        Files are read from /data/prompts/{name}.txt
        """
        if use_fun:
            return self.get('fun_prompt', 'You are a helpful assistant.')

        return self.get('system_prompt', 'You are a helpful assistant.')
    
    def get_api_clients_config(self) -> Dict[str, str]:
        """Get API client configuration"""
        return {
            'openai_api_key': self.get_required('openai_api_key'),
            'openrouter_api_key': self.get_required('openrouter_api_key'),
        }
    
    def get_data_files_config(self) -> Dict[str, str]:
        """Get data file paths configuration"""
        return {
            'data_directory': self.get('data_directory'),
            'user_quotas_file': self.get('user_quotas_file'),
            'conversation_history_file': self.get('conversation_history_file'),
            'reminders_file': self.get('reminders_file'),
            'user_timezones_file': self.get('user_timezones_file'),
            'log_file': self.get('log_file'),
        }
    
    def validate_configuration(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Check required values
        required_keys = [
            'bot_token', 'openai_api_key', 'openrouter_api_key'
        ]
        
        for key in required_keys:
            if not self.get(key):
                issues.append(f"Missing required configuration: {key}")
        
        # Validate data directory
        data_dir = self.get('data_directory')
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir, exist_ok=True)
                logger.info(f"Created data directory: {data_dir}")
            except Exception as e:
                issues.append(f"Cannot create data directory {data_dir}: {e}")
        
        return issues
    
    def reload_configuration(self):
        """Reload configuration from environment"""
        self._config.clear()
        self._load_configuration()
        logger.info("Configuration reloaded")
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get configuration debug information (excluding sensitive data)"""
        debug_info = {}
        
        # Safe keys that don't contain sensitive information
        safe_keys = [
            'bot_tag', 'command_prefix', 'default_model', 'max_tokens_default',
            'data_directory', 'user_quotas_file', 'conversation_history_file',
            'reminders_file', 'user_timezones_file', 'log_file'
        ]
        
        for key in safe_keys:
            debug_info[key] = self.get(key)
        
        # Add counts for admin/unlimited users
        debug_info['admin_count'] = len(self.get('admin_ids', []))
        debug_info['unlimited_users_count'] = len(self.get('unlimited_user_ids', []))
        
        # Add boolean flags for optional features
        debug_info['has_duck_proxy'] = bool(self.get('duck_proxy'))
        
        return debug_info


# Create global configuration instance
config = ConfigManager()


# Export for easy importing
__all__ = [
    'ConfigManager',
    'config'
]