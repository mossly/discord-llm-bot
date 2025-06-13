"""
Attachment processing utilities for Discord LLM bot
Handles file attachments and image processing
"""

import aiohttp
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


async def process_attachments(
    prompt: str, 
    attachments: List, 
    is_slash: bool = False
) -> Tuple[str, Optional[str]]:
    """
    Process Discord message attachments and return updated prompt and image URL
    
    Args:
        prompt: Original text prompt
        attachments: List of Discord attachment objects
        is_slash: Whether this is from a slash command (affects how files are read)
        
    Returns:
        Tuple of (final_prompt, image_url)
    """
    image_url = None
    final_prompt = prompt
    
    if not attachments:
        return final_prompt, image_url
    
    for attachment in attachments:
        filename = attachment.filename.lower()
        
        # Handle text files
        if filename.endswith(".txt"):
            try:
                text_content = await _read_text_attachment(attachment, is_slash)
                if text_content:
                    final_prompt = text_content  # Replace prompt with file content
                    logger.info(f"Processed text attachment: {attachment.filename}")
            except Exception as e:
                logger.exception(f"Error processing text attachment {attachment.filename}: {e}")
        
        # Handle image files
        elif _is_image_file(filename) and not image_url:
            image_url = attachment.proxy_url or attachment.url
            logger.info(f"Processed image attachment: {attachment.filename}")
    
    return final_prompt, image_url


async def _read_text_attachment(attachment, is_slash: bool) -> Optional[str]:
    """Read content from a text attachment"""
    try:
        if is_slash:
            # For slash commands, read directly from attachment
            file_bytes = await attachment.read()
            return file_bytes.decode("utf-8")
        else:
            # For regular messages, fetch from URL
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(
                            f"Failed to download attachment: {attachment.url} "
                            f"with status {response.status}"
                        )
                        return None
    except UnicodeDecodeError as e:
        logger.error(f"Text file encoding error for {attachment.filename}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading text attachment: {e}")
        return None


def _is_image_file(filename: str) -> bool:
    """Check if filename indicates an image file"""
    image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")
    return filename.endswith(image_extensions)


def get_supported_file_types() -> dict:
    """Get dictionary of supported file types and their descriptions"""
    return {
        "text": {
            "extensions": [".txt"],
            "description": "Text files (replaces the prompt with file content)",
            "max_size": "10MB"
        },
        "images": {
            "extensions": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"],
            "description": "Image files (analyzed by vision-capable models)",
            "max_size": "25MB"
        }
    }


async def validate_attachments(attachments: List) -> Tuple[bool, Optional[str]]:
    """
    Validate attachments before processing
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not attachments:
        return True, None
    
    supported_types = get_supported_file_types()
    text_extensions = supported_types["text"]["extensions"]
    image_extensions = supported_types["images"]["extensions"]
    all_extensions = text_extensions + image_extensions
    
    for attachment in attachments:
        filename = attachment.filename.lower()
        
        # Check if file type is supported
        if not any(filename.endswith(ext) for ext in all_extensions):
            return False, (
                f"Unsupported file type: {attachment.filename}. "
                f"Supported types: {', '.join(all_extensions)}"
            )
        
        # Check file size (Discord limit is 25MB for most servers)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        if attachment.size > max_size:
            return False, (
                f"File too large: {attachment.filename} ({attachment.size / 1024 / 1024:.1f}MB). "
                f"Maximum size: 25MB"
            )
    
    return True, None


# Export functions for easy importing
__all__ = [
    'process_attachments',
    'get_supported_file_types', 
    'validate_attachments'
]