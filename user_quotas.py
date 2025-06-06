import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class UserQuotaManager:
    def __init__(self, quota_file: str = "/data/user_quotas.json"):
        # Ensure /data directory exists
        os.makedirs("/data", exist_ok=True)
        self.quota_file = quota_file
        self.quotas = self._load_quotas()
        self.default_monthly_quota = 1.0  # $1 per month default
        self.unlimited_user_ids = self._load_unlimited_users()
        
    def _load_quotas(self) -> Dict:
        """Load user quotas from JSON file"""
        if os.path.exists(self.quota_file):
            try:
                with open(self.quota_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading quota file: {e}")
                return {}
        return {}
    
    def _load_unlimited_users(self) -> set:
        """Load unlimited quota user IDs from environment variable"""
        unlimited_ids = set()
        env_unlimited = os.getenv('BOT_UNLIMITED_USER_IDS', '')
        if env_unlimited:
            try:
                unlimited_ids.update(uid.strip() for uid in env_unlimited.split(',') if uid.strip())
                logger.info(f"Loaded {len(unlimited_ids)} unlimited quota users from environment")
            except Exception as e:
                logger.error(f"Error loading unlimited user IDs: {e}")
        return unlimited_ids
    
    def _save_quotas(self):
        """Save user quotas to JSON file"""
        try:
            with open(self.quota_file, 'w') as f:
                json.dump(self.quotas, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving quota file: {e}")
    
    def _get_current_month_key(self) -> str:
        """Get current month key for quota tracking (YYYY-MM format)"""
        return datetime.now(timezone.utc).strftime("%Y-%m")
    
    def _initialize_user(self, user_id: str):
        """Initialize a new user with default quota"""
        if user_id not in self.quotas:
            is_unlimited = user_id in self.unlimited_user_ids
            self.quotas[user_id] = {
                "monthly_quota": float('inf') if is_unlimited else self.default_monthly_quota,
                "usage": {}
            }
            if is_unlimited:
                logger.info(f"Initialized unlimited quota user: {user_id}")
            self._save_quotas()
    
    def get_user_quota(self, user_id: str) -> float:
        """Get user's monthly quota limit"""
        self._initialize_user(user_id)
        return self.quotas[user_id]["monthly_quota"]
    
    def get_user_usage(self, user_id: str, month: str = None) -> float:
        """Get user's usage for specified month (defaults to current month)"""
        self._initialize_user(user_id)
        month = month or self._get_current_month_key()
        return self.quotas[user_id]["usage"].get(month, 0.0)
    
    def get_remaining_quota(self, user_id: str) -> float:
        """Get user's remaining quota for current month"""
        quota = self.get_user_quota(user_id)
        if quota == float('inf'):
            return float('inf')
        usage = self.get_user_usage(user_id)
        return max(0.0, quota - usage)
    
    def can_afford(self, user_id: str, cost: float) -> bool:
        """Check if user can afford the specified cost"""
        if user_id in self.unlimited_user_ids:
            return True
        remaining = self.get_remaining_quota(user_id)
        return remaining >= cost
    
    def add_usage(self, user_id: str, cost: float) -> bool:
        """Add usage cost to user's monthly total. Returns True if successful."""
        if not self.can_afford(user_id, cost):
            return False
            
        self._initialize_user(user_id)
        month = self._get_current_month_key()
        
        if "usage" not in self.quotas[user_id]:
            self.quotas[user_id]["usage"] = {}
            
        current_usage = self.quotas[user_id]["usage"].get(month, 0.0)
        self.quotas[user_id]["usage"][month] = current_usage + cost
        
        self._save_quotas()
        logger.info(f"User {user_id} used ${cost:.4f}, total this month: ${current_usage + cost:.4f}")
        return True
    
    def set_user_quota(self, user_id: str, quota: float):
        """Set user's monthly quota (admin function)"""
        self._initialize_user(user_id)
        self.quotas[user_id]["monthly_quota"] = quota
        self._save_quotas()
        logger.info(f"Set user {user_id} quota to ${quota:.2f}")
    
    def reset_user_usage(self, user_id: str, month: str = None):
        """Reset user's usage for specified month (admin function)"""
        self._initialize_user(user_id)
        month = month or self._get_current_month_key()
        if "usage" in self.quotas[user_id]:
            self.quotas[user_id]["usage"][month] = 0.0
            self._save_quotas()
            logger.info(f"Reset user {user_id} usage for {month}")
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get comprehensive user statistics"""
        self._initialize_user(user_id)
        current_month = self._get_current_month_key()
        usage = self.get_user_usage(user_id, current_month)
        quota = self.get_user_quota(user_id)
        remaining = self.get_remaining_quota(user_id)
        
        return {
            "user_id": user_id,
            "monthly_quota": quota,
            "current_usage": usage,
            "remaining_quota": remaining,
            "is_unlimited": user_id in self.unlimited_user_ids,
            "current_month": current_month
        }
    
    def get_all_users_stats(self) -> Dict:
        """Get statistics for all users (admin function)"""
        current_month = self._get_current_month_key()
        stats = {}
        for user_id in self.quotas:
            stats[user_id] = self.get_user_stats(user_id)
        return stats

# Global instance
quota_manager = UserQuotaManager()