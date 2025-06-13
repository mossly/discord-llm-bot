"""
Utility modules for Discord LLM bot
Contains shared utility functions and classes used across the application
"""

# Import main utility classes for easy access
from .attachment_handler import process_attachments, validate_attachments, get_supported_file_types
from .conversation_logger import ConversationLogger, conversation_logger
from .quota_validator import QuotaValidator, quota_validator
from .response_formatter import extract_footnotes, build_standardized_footer, format_usage_stats
from .embed_utils import create_error_embed, create_success_embed, send_embed, split_embed
from .reminder_manager import reminder_manager

__all__ = [
    # Attachment handling
    'process_attachments',
    'validate_attachments', 
    'get_supported_file_types',
    
    # Conversation logging
    'ConversationLogger',
    'conversation_logger',
    
    # Quota validation
    'QuotaValidator', 
    'quota_validator',
    
    # Response formatting
    'extract_footnotes',
    'build_standardized_footer',
    'format_usage_stats',
    
    # Embed utilities
    'create_error_embed',
    'create_success_embed',
    'send_embed',
    'split_embed',
    
    # Reminder management
    'reminder_manager',
]