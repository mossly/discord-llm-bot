"""
Discord message search tool for searching through existing server messages
"""

from typing import Dict, Any, List, Optional, Union
from .base_tool import BaseTool
import discord
import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone
import time

logger = logging.getLogger(__name__)


class DiscordMessageSearchTool(BaseTool):
    """Tool for searching through Discord message history in real-time"""
    
    def __init__(self, bot: discord.Client):
        super().__init__()
        self.bot = bot
        self.max_search_limit = 10000  # Safety limit
        self.rate_limit_delay = 0.1  # Delay between API calls to respect rate limits
    
    @property
    def name(self) -> str:
        return "search_discord_messages"
    
    @property
    def description(self) -> str:
        return "Search through Discord message history in real-time. Useful for finding past discussions, specific messages, or context from server conversations. Only searches channels the bot has access to."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or phrase to find in messages (case-insensitive by default)"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Specific channel ID to search in (optional). If not provided, searches accessible channels in current server."
                },
                "server_id": {
                    "type": "string", 
                    "description": "Specific server/guild ID to search in (optional). Searches all accessible channels in the server."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to search through (default: 1000, max: 10000)",
                    "default": 1000
                },
                "author_id": {
                    "type": "string",
                    "description": "Search only messages from specific user ID (optional)"
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range to search within: '1h', '6h', '1d', '7d', '30d' (optional)"
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether search should be case-sensitive (default: false)",
                    "default": False
                },
                "exclude_bots": {
                    "type": "boolean", 
                    "description": "Whether to exclude messages from bots (default: true)",
                    "default": True
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching results to return (default: 20, max: 50)",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    
    def _parse_time_range(self, time_range: str) -> Optional[datetime]:
        """Parse time range string and return cutoff datetime"""
        if not time_range:
            return None
            
        time_map = {
            'h': 'hours', 'd': 'days', 'm': 'minutes', 'w': 'weeks'
        }
        
        # Extract number and unit (e.g., "7d" -> 7, "d")
        match = re.match(r'^(\d+)([hdmw])$', time_range.lower())
        if not match:
            return None
            
        amount, unit = match.groups()
        amount = int(amount)
        
        if unit not in time_map:
            return None
            
        kwargs = {time_map[unit]: amount}
        cutoff_time = datetime.now(timezone.utc) - timedelta(**kwargs)
        return cutoff_time
    
    def _should_include_message(self, message: discord.Message, query: str, 
                               case_sensitive: bool, exclude_bots: bool, 
                               author_id: Optional[str], cutoff_time: Optional[datetime]) -> bool:
        """Check if message matches search criteria"""
        # Time filter
        if cutoff_time and message.created_at < cutoff_time:
            return False
            
        # Bot filter
        if exclude_bots and message.author.bot:
            return False
            
        # Author filter
        if author_id and str(message.author.id) != author_id:
            return False
            
        # Content search
        content = message.content
        if not content:  # Skip empty messages
            return False
            
        # Case sensitivity
        if case_sensitive:
            return query in content
        else:
            return query.lower() in content.lower()
    
    def _format_message_result(self, message: discord.Message) -> Dict[str, Any]:
        """Format message into result dictionary"""
        return {
            "message_id": str(message.id),
            "content": message.content,
            "author": {
                "id": str(message.author.id),
                "name": message.author.name,
                "display_name": message.author.display_name,
                "is_bot": message.author.bot
            },
            "channel": {
                "id": str(message.channel.id),
                "name": message.channel.name,
                "type": str(message.channel.type)
            },
            "server": {
                "id": str(message.guild.id) if message.guild else None,
                "name": message.guild.name if message.guild else None
            },
            "timestamp": message.created_at.isoformat(),
            "jump_url": message.jump_url,
            "has_attachments": len(message.attachments) > 0,
            "attachment_count": len(message.attachments),
            "reply_to": str(message.reference.message_id) if message.reference else None
        }
    
    async def _search_channel(self, channel: discord.TextChannel, query: str,
                             limit: int, case_sensitive: bool, exclude_bots: bool,
                             author_id: Optional[str], cutoff_time: Optional[datetime],
                             max_results: int) -> List[Dict[str, Any]]:
        """Search through a specific channel"""
        results = []
        messages_searched = 0
        
        try:
            async for message in channel.history(limit=limit):
                messages_searched += 1
                
                if self._should_include_message(message, query, case_sensitive, 
                                               exclude_bots, author_id, cutoff_time):
                    results.append(self._format_message_result(message))
                    
                    # Stop if we have enough results
                    if len(results) >= max_results:
                        break
                
                # Rate limiting
                if messages_searched % 100 == 0:
                    await asyncio.sleep(self.rate_limit_delay)
                    
        except discord.Forbidden:
            logger.warning(f"No permission to read history in channel {channel.name}")
        except Exception as e:
            logger.error(f"Error searching channel {channel.name}: {e}")
            
        return results
    
    async def execute(self, query: str, channel_id: Optional[str] = None,
                     server_id: Optional[str] = None, limit: int = 1000,
                     author_id: Optional[str] = None, time_range: Optional[str] = None,
                     case_sensitive: bool = False, exclude_bots: bool = True,
                     max_results: int = 20) -> Dict[str, Any]:
        """Execute Discord message search"""
        try:
            # Validate parameters
            if not query or len(query.strip()) < 2:
                return {
                    "success": False,
                    "error": "Query must be at least 2 characters long"
                }
            
            # Apply safety limits
            limit = min(limit, self.max_search_limit)
            max_results = min(max_results, 50)
            
            # Parse time range
            cutoff_time = self._parse_time_range(time_range) if time_range else None
            
            results = []
            channels_searched = []
            search_stats = {
                "channels_searched": 0,
                "messages_searched": 0,
                "permission_errors": 0
            }
            
            start_time = time.time()
            
            # Search specific channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "success": False,
                        "error": f"Channel with ID {channel_id} not found or not accessible"
                    }
                
                if not isinstance(channel, discord.TextChannel):
                    return {
                        "success": False,
                        "error": f"Channel {channel_id} is not a text channel"
                    }
                
                channel_results = await self._search_channel(
                    channel, query, limit, case_sensitive, exclude_bots,
                    author_id, cutoff_time, max_results
                )
                results.extend(channel_results)
                channels_searched.append(channel.name)
                search_stats["channels_searched"] = 1
                
            # Search specific server
            elif server_id:
                guild = self.bot.get_guild(int(server_id))
                if not guild:
                    return {
                        "success": False,
                        "error": f"Server with ID {server_id} not found or not accessible"
                    }
                
                for channel in guild.text_channels:
                    if len(results) >= max_results:
                        break
                        
                    try:
                        channel_results = await self._search_channel(
                            channel, query, limit // len(guild.text_channels) + 1,
                            case_sensitive, exclude_bots, author_id, cutoff_time,
                            max_results - len(results)
                        )
                        results.extend(channel_results)
                        channels_searched.append(channel.name)
                        search_stats["channels_searched"] += 1
                        
                    except discord.Forbidden:
                        search_stats["permission_errors"] += 1
                    
                    # Rate limiting between channels
                    await asyncio.sleep(self.rate_limit_delay)
            
            # Search all accessible servers (limited scope for performance)
            else:
                # Limit to first few guilds to prevent excessive API usage
                guilds_to_search = list(self.bot.guilds)[:3]  # Max 3 servers
                
                for guild in guilds_to_search:
                    if len(results) >= max_results:
                        break
                        
                    # Limit channels per guild
                    channels_to_search = guild.text_channels[:5]  # Max 5 channels per server
                    
                    for channel in channels_to_search:
                        if len(results) >= max_results:
                            break
                            
                        try:
                            channel_results = await self._search_channel(
                                channel, query, min(limit // 10, 100),  # Reduced limit for broad search
                                case_sensitive, exclude_bots, author_id, cutoff_time,
                                max_results - len(results)
                            )
                            results.extend(channel_results)
                            channels_searched.append(f"{guild.name}#{channel.name}")
                            search_stats["channels_searched"] += 1
                            
                        except discord.Forbidden:
                            search_stats["permission_errors"] += 1
                        
                        # Rate limiting
                        await asyncio.sleep(self.rate_limit_delay)
            
            elapsed_time = time.time() - start_time
            
            # Sort results by timestamp (newest first)
            results.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return {
                "success": True,
                "results": results,
                "query": query,
                "total_results": len(results),
                "search_stats": {
                    **search_stats,
                    "elapsed_time": round(elapsed_time, 2),
                    "channels_searched_names": channels_searched[:10]  # Limit for readability
                },
                "filters_applied": {
                    "case_sensitive": case_sensitive,
                    "exclude_bots": exclude_bots,
                    "author_id": author_id,
                    "time_range": time_range,
                    "cutoff_time": cutoff_time.isoformat() if cutoff_time else None
                },
                "message": f"Found {len(results)} message(s) matching '{query}' across {search_stats['channels_searched']} channel(s)"
            }
            
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid parameter: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error in Discord message search: {e}")
            return {
                "success": False,
                "error": f"Search failed: {str(e)}"
            }
    
    def get_usage_summary(self) -> str:
        """Get a summary of tool usage for monitoring"""
        return f"DiscordMessageSearch: {self.usage_count} searches, {self.error_count} errors"