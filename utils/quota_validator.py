"""
Quota validation utilities for Discord LLM bot
Handles pre-request quota checking and post-request usage tracking
"""

import logging
from typing import Tuple, Optional
from user_quotas import quota_manager

logger = logging.getLogger(__name__)


class QuotaValidator:
    """Handles quota validation and usage tracking"""
    
    def __init__(self):
        self.quota_manager = quota_manager
    
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


# Create a global instance for easy access
quota_validator = QuotaValidator()


# Export for easy importing
__all__ = [
    'QuotaValidator',
    'quota_validator'
]