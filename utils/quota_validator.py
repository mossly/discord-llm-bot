"""
Unified quota management system for Discord LLM bot
Handles all quota operations, validation, and usage tracking
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict
from config_manager import config

logger = logging.getLogger(__name__)


class QuotaManager:
    """Unified quota management system - single source of truth for all quota operations"""
    
    def __init__(self, quota_file: str = None):
        # Use config manager for file path
        self.quota_file = quota_file or config.get('user_quotas_file', '/data/user_quotas.json')
        # Ensure data directory exists
        data_dir = os.path.dirname(self.quota_file)
        os.makedirs(data_dir, exist_ok=True)
        
        self.quotas = self._load_quotas()
        self.default_monthly_quota = 1.0  # $1 per month default
        self.unlimited_user_ids = set(config.get('unlimited_user_ids', []))
        
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


class QuotaValidator:
    """Validation interface for quota operations - maintains backward compatibility"""
    
    def __init__(self):
        self.quota_manager = QuotaManager()
    
    def check_user_quota(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if user has sufficient quota for a request
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Tuple of (can_proceed, error_message)
        """
        try:
            remaining_quota = self.quota_manager.get_remaining_quota(user_id)
            
            # Check if quota is completely exhausted
            if remaining_quota == 0:
                return False, (
                    "❌ **Quota Exceeded**: You've reached your monthly usage limit. "
                    "Your quota resets at the beginning of each month."
                )
            
            # Check if quota is very low (less than 1 cent remaining)
            elif remaining_quota != float('inf') and remaining_quota < 0.01:
                return False, (
                    f"⚠️ **Low Quota**: You have ${remaining_quota:.4f} remaining this month. "
                    f"Please be mindful of usage."
                )
            
            # User has sufficient quota
            return True, None
            
        except Exception as e:
            logger.error(f"Error checking quota for user {user_id}: {e}")
            # Allow request to proceed on quota check errors to avoid blocking users
            return True, None
    
    def can_afford_request(self, user_id: str, estimated_cost: float) -> bool:
        """
        Check if user can afford a specific estimated cost
        
        Args:
            user_id: Discord user ID
            estimated_cost: Estimated cost in dollars
            
        Returns:
            True if user can afford the request
        """
        try:
            return self.quota_manager.can_afford(user_id, estimated_cost)
        except Exception as e:
            logger.error(f"Error checking affordability for user {user_id}: {e}")
            # Allow request on error to avoid blocking
            return True
    
    def track_usage(self, user_id: str, actual_cost: float) -> bool:
        """
        Track actual usage after a request completes
        
        Args:
            user_id: Discord user ID
            actual_cost: Actual cost incurred
            
        Returns:
            True if usage was tracked successfully
        """
        try:
            if actual_cost > 0:
                success = self.quota_manager.add_usage(user_id, actual_cost)
                if success:
                    logger.info(f"Tracked ${actual_cost:.4f} usage for user {user_id}")
                else:
                    logger.warning(f"Failed to track usage for user {user_id}")
                return success
            return True
        except Exception as e:
            logger.error(f"Error tracking usage for user {user_id}: {e}")
            return False
    
    def get_user_quota_info(self, user_id: str) -> dict:
        """
        Get comprehensive quota information for a user
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Dictionary with quota information
        """
        try:
            stats = self.quota_manager.get_user_stats(user_id)
            return {
                "monthly_quota": stats["monthly_quota"],
                "current_usage": stats["current_usage"],
                "remaining_quota": stats["remaining_quota"],
                "is_unlimited": stats["is_unlimited"],
                "current_month": stats["current_month"],
                "usage_percentage": (
                    (stats["current_usage"] / stats["monthly_quota"] * 100)
                    if stats["monthly_quota"] != float('inf') else 0
                )
            }
        except Exception as e:
            logger.error(f"Error getting quota info for user {user_id}: {e}")
            return {
                "monthly_quota": 0.0,
                "current_usage": 0.0,
                "remaining_quota": 0.0,
                "is_unlimited": False,
                "current_month": "unknown",
                "usage_percentage": 0.0
            }
    
    def format_quota_status(self, user_id: str) -> str:
        """
        Format quota status into a human-readable string
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Formatted quota status string
        """
        info = self.get_user_quota_info(user_id)
        
        if info["is_unlimited"]:
            return "**Quota Status**: Unlimited usage"
        
        quota = info["monthly_quota"]
        used = info["current_usage"]
        remaining = info["remaining_quota"]
        percentage = info["usage_percentage"]
        
        # Format amounts
        quota_str = f"${quota:.2f}" if quota < 10 else f"${quota:.1f}"
        used_str = f"${used:.3f}" if used < 0.01 else f"${used:.2f}"
        remaining_str = f"${remaining:.3f}" if remaining < 0.01 else f"${remaining:.2f}"
        
        # Create status message
        status = f"**Quota Status**: {used_str} used of {quota_str} ({percentage:.1f}%)\n"
        status += f"**Remaining**: {remaining_str}"
        
        # Add warning if quota is low
        if remaining < 0.10:  # Less than 10 cents
            status += " ⚠️ **Low quota**"
        
        return status


# Create global instances for easy access
quota_manager = QuotaManager()
quota_validator = QuotaValidator()


# Export for easy importing
__all__ = [
    'QuotaManager',
    'QuotaValidator', 
    'quota_manager',
    'quota_validator'
]