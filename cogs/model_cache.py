"""
High-performance model configuration caching system
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Set, Optional, Any
from threading import RLock
import hashlib

logger = logging.getLogger(__name__)


class ModelCache:
    """High-performance in-memory cache for model configurations"""
    
    def __init__(self):
        self._cache_lock = RLock()
        
        # Core cache data
        self._models_config: Dict[str, Dict] = {}
        self._available_models_cache: Dict[str, Dict[str, Dict]] = {}  # user_type -> models
        self._admin_ids: Set[int] = set()
        
        # Cache metadata
        self._last_file_check: float = 0
        self._last_file_mtime: float = 0
        self._file_check_interval: float = 5.0  # Check file every 5 seconds
        self._cache_version: int = 0
        
        # Performance tracking
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._last_reload_time: float = 0
        
        # File paths
        self._models_config_file = "/data/models_config.json"
        self._models_config_default_file = "models_config_default.json"
        
        # Initialize cache
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Initialize the cache with data from files"""
        with self._cache_lock:
            logger.info("Initializing model cache...")
            start_time = time.time()
            
            # Load admin IDs
            self._admin_ids = self._load_admin_ids()
            
            # Load model configurations
            self._models_config = self._load_models_config()
            
            # Precompute available models for different user types
            self._rebuild_available_models_cache()
            
            # Mark cache as initialized
            self._last_reload_time = time.time()
            self._cache_version += 1
            
            elapsed = time.time() - start_time
            logger.info(f"Model cache initialized in {elapsed:.3f}s with {len(self._models_config)} models")
    
    def _load_admin_ids(self) -> Set[int]:
        """Load admin IDs from environment variable or file"""
        admin_ids = set()
        
        # Try environment variable first
        env_admins = os.getenv('BOT_ADMIN_IDS', '')
        if env_admins:
            try:
                admin_ids.update(int(uid.strip()) for uid in env_admins.split(',') if uid.strip())
                logger.info(f"Loaded {len(admin_ids)} admin users from environment")
            except ValueError:
                logger.warning("Invalid admin IDs in BOT_ADMIN_IDS environment variable")
        
        # Try loading from file
        admin_file = '/data/admin_ids.txt'
        if os.path.exists(admin_file):
            try:
                with open(admin_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            try:
                                admin_ids.add(int(line))
                            except ValueError:
                                logger.warning(f"Invalid admin ID: {line}")
                logger.info(f"Loaded admin IDs from file")
            except IOError as e:
                logger.warning(f"Could not read admin file: {e}")
        
        return admin_ids
    
    def _load_models_config(self) -> Dict[str, Dict]:
        """Load models configuration with fallback to default"""
        config = {}
        
        # Try to load from data directory
        if os.path.exists(self._models_config_file):
            try:
                with open(self._models_config_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded models config from {self._models_config_file}")
                    
                # Update file modification time
                self._last_file_mtime = os.path.getmtime(self._models_config_file)
                return config
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load models config: {e}")
        
        # Fall back to default
        if os.path.exists(self._models_config_default_file):
            try:
                with open(self._models_config_default_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded default models config")
                    
                # Copy to data directory
                self._ensure_data_dir()
                try:
                    import shutil
                    shutil.copy2(self._models_config_default_file, self._models_config_file)
                    logger.info("Copied default config to data directory")
                except Exception as e:
                    logger.warning(f"Could not copy default config: {e}")
                
                return config
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load default config: {e}")
        
        logger.warning("No model configuration found, starting with empty config")
        return {}
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        os.makedirs("/data", exist_ok=True)
    
    def _rebuild_available_models_cache(self):
        """Rebuild the available models cache for different user types"""
        self._available_models_cache.clear()
        
        # Cache for regular users (non-admin)
        user_models = {}
        # Cache for admin users
        admin_models = {}
        
        for model_key, config in self._models_config.items():
            # Skip non-dict entries (comments, etc.)
            if not isinstance(config, dict):
                continue
                
            # Only include enabled models
            if not config.get("enabled", True):
                continue
            
            # Add to admin cache (admins see everything)
            admin_models[model_key] = config
            
            # Add to user cache only if not admin-only
            if not config.get("admin_only", False):
                user_models[model_key] = config
        
        self._available_models_cache = {
            "user": user_models,
            "admin": admin_models
        }
        
        logger.info(f"Rebuilt model cache: {len(user_models)} public, {len(admin_models)} total models")
    
    def _check_file_changes(self) -> bool:
        """Check if model config file has been modified"""
        current_time = time.time()
        
        # Only check file periodically to avoid excessive I/O
        if current_time - self._last_file_check < self._file_check_interval:
            return False
        
        self._last_file_check = current_time
        
        if not os.path.exists(self._models_config_file):
            return False
        
        try:
            current_mtime = os.path.getmtime(self._models_config_file)
            if current_mtime > self._last_file_mtime:
                logger.info("Model config file has been modified, reloading cache")
                return True
        except OSError:
            pass
        
        return False
    
    def _maybe_reload_cache(self):
        """Reload cache if file has changed"""
        if self._check_file_changes():
            with self._cache_lock:
                # Double-check under lock
                if self._check_file_changes():
                    logger.info("Reloading model cache due to file changes")
                    self._models_config = self._load_models_config()
                    self._rebuild_available_models_cache()
                    self._cache_version += 1
                    self._last_reload_time = time.time()
    
    def get_model_config(self, model_key: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific model (optimized)"""
        # Check for file changes
        self._maybe_reload_cache()
        
        with self._cache_lock:
            config = self._models_config.get(model_key)
            if config:
                self._cache_hits += 1
            else:
                self._cache_misses += 1
            return config
    
    def get_available_models(self, user_id: Optional[int] = None) -> Dict[str, Dict]:
        """Get models available to a user (highly optimized)"""
        # Check for file changes
        self._maybe_reload_cache()
        
        with self._cache_lock:
            # Determine user type
            is_admin = user_id and user_id in self._admin_ids
            cache_key = "admin" if is_admin else "user"
            
            models = self._available_models_cache.get(cache_key, {})
            self._cache_hits += 1
            return models.copy()  # Return copy to prevent external modification
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin (optimized)"""
        with self._cache_lock:
            return user_id in self._admin_ids
    
    def update_model_config(self, model_key: str, config: Dict[str, Any]):
        """Update a model configuration in cache and file"""
        with self._cache_lock:
            # Update in-memory cache
            self._models_config[model_key] = config
            
            # Rebuild available models cache
            self._rebuild_available_models_cache()
            
            # Save to file
            self._save_models_config()
            
            # Update cache metadata
            self._cache_version += 1
            
            logger.info(f"Updated model config for {model_key}")
    
    def remove_model_config(self, model_key: str) -> bool:
        """Remove a model configuration"""
        with self._cache_lock:
            if model_key in self._models_config:
                del self._models_config[model_key]
                self._rebuild_available_models_cache()
                self._save_models_config()
                self._cache_version += 1
                logger.info(f"Removed model config for {model_key}")
                return True
            return False
    
    def _save_models_config(self):
        """Save models configuration to file (optimized)"""
        try:
            self._ensure_data_dir()
            
            # Use atomic write to prevent corruption
            temp_file = self._models_config_file + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(self._models_config, f, indent=2)
            
            # Atomic rename
            import shutil
            shutil.move(temp_file, self._models_config_file)
            
            # Update modification time
            self._last_file_mtime = os.path.getmtime(self._models_config_file)
            
            logger.debug(f"Saved models config to {self._models_config_file}")
        except Exception as e:
            logger.error(f"Failed to save models config: {e}")
    
    def reload_cache(self):
        """Force reload the entire cache"""
        with self._cache_lock:
            logger.info("Force reloading model cache")
            self._initialize_cache()
    
    def add_admin(self, user_id: int):
        """Add an admin user"""
        with self._cache_lock:
            self._admin_ids.add(user_id)
            # Rebuild cache since admin status affects available models
            self._rebuild_available_models_cache()
            logger.info(f"Added admin user: {user_id}")
    
    def remove_admin(self, user_id: int):
        """Remove an admin user"""
        with self._cache_lock:
            self._admin_ids.discard(user_id)
            self._rebuild_available_models_cache()
            logger.info(f"Removed admin user: {user_id}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        with self._cache_lock:
            total_requests = self._cache_hits + self._cache_misses
            hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "models_count": len(self._models_config),
                "admin_count": len(self._admin_ids),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "hit_rate_percent": round(hit_rate, 2),
                "cache_version": self._cache_version,
                "last_reload": self._last_reload_time,
                "uptime_seconds": time.time() - self._last_reload_time
            }
    
    def warm_cache(self):
        """Warm up the cache by preloading common operations"""
        logger.info("Warming up model cache...")
        start_time = time.time()
        
        # Preload common operations
        self.get_available_models(None)  # Anonymous user
        
        # Simulate some admin users
        for admin_id in list(self._admin_ids)[:5]:  # First 5 admins
            self.get_available_models(admin_id)
        
        # Preload all model configs
        for model_key in self._models_config.keys():
            self.get_model_config(model_key)
        
        elapsed = time.time() - start_time
        logger.info(f"Cache warmed up in {elapsed:.3f}s")


# Global cache instance
_model_cache: Optional[ModelCache] = None


def get_model_cache() -> ModelCache:
    """Get the global model cache instance"""
    global _model_cache
    if _model_cache is None:
        _model_cache = ModelCache()
    return _model_cache


def initialize_model_cache():
    """Initialize the global model cache"""
    global _model_cache
    if _model_cache is None:
        _model_cache = ModelCache()
        _model_cache.warm_cache()
    return _model_cache