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
        return "Search through Discord message history in real-time. Can search by content query, by user, or both. Useful for finding past discussions, specific messages, recent user activity, or context from server conversations. Note: You can only search messages in servers and channels where you have access."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or phrase to find in messages (optional). If not provided, returns recent messages from the specified user or channel."
                },
                "channel_id": {
                    "type": "string",
                    "description": "Specific channel ID to search in (optional). If not provided, searches accessible channels in current server."
                },
                "channel_name": {
                    "type": "string",
                    "description": "Specific channel name to search in (optional). Will be resolved to channel ID automatically."
                },
                "server_id": {
                    "type": "string", 
                    "description": "Specific server/guild ID to search in (optional). Searches all accessible channels in the server."
                },
                "server_name": {
                    "type": "string",
                    "description": "Specific server/guild name to search in (optional). Will be resolved to server ID automatically."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to search through (default: 10000, max: 10000)",
                    "default": 10000
                },
                "author_id": {
                    "type": "string",
                    "description": "Search only messages from specific user ID (optional)"
                },
                "author_name": {
                    "type": "string",
                    "description": "Search only messages from specific username or display name (optional). Will be resolved to user ID automatically."
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
            "required": []
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
    
    async def _resolve_user_id(self, author_name: str, guild_id: Optional[int] = None) -> Optional[str]:
        """Resolve username/display name to user ID"""
        if not author_name:
            return None
            
        author_name_lower = author_name.lower().strip()
        best_match = None
        exact_match = None
        
        # Search in specific guild if provided
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                for member in guild.members:
                    # Exact username match (case-insensitive)
                    if member.name.lower() == author_name_lower:
                        exact_match = str(member.id)
                        break
                    # Exact display name match (case-insensitive)  
                    if member.display_name.lower() == author_name_lower:
                        exact_match = str(member.id)
                        break
                    # Partial matches for fallback
                    if (author_name_lower in member.name.lower() or 
                        author_name_lower in member.display_name.lower()):
                        if not best_match:  # First partial match
                            best_match = str(member.id)
                            
        # If no guild specified or no match found, search across all accessible guilds
        if not exact_match and not best_match:
            for guild in self.bot.guilds:
                for member in guild.members:
                    # Exact username match (case-insensitive)
                    if member.name.lower() == author_name_lower:
                        exact_match = str(member.id)
                        break
                    # Exact display name match (case-insensitive)
                    if member.display_name.lower() == author_name_lower:
                        exact_match = str(member.id)
                        break
                    # Partial matches for fallback
                    if (author_name_lower in member.name.lower() or 
                        author_name_lower in member.display_name.lower()):
                        if not best_match:  # First partial match
                            best_match = str(member.id)
                            
                if exact_match:  # Break out of outer loop if exact match found
                    break
        
        # Return exact match first, then partial match, then None
        return exact_match or best_match
    
    async def _resolve_channel_id(self, channel_name: str, guild_id: Optional[int] = None) -> Optional[str]:
        """Resolve channel name to channel ID"""
        if not channel_name:
            return None
            
        channel_name_lower = channel_name.lower().strip()
        best_match = None
        exact_match = None
        
        # Search in specific guild if provided
        if guild_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                for channel in guild.text_channels:
                    # Exact name match (case-insensitive)
                    if channel.name.lower() == channel_name_lower:
                        exact_match = str(channel.id)
                        break
                    # Partial matches for fallback
                    if channel_name_lower in channel.name.lower():
                        if not best_match:  # First partial match
                            best_match = str(channel.id)
        
        # If no guild specified or no match found, search across all accessible guilds
        if not exact_match and not best_match:
            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    # Exact name match (case-insensitive)
                    if channel.name.lower() == channel_name_lower:
                        exact_match = str(channel.id)
                        break
                    # Partial matches for fallback
                    if channel_name_lower in channel.name.lower():
                        if not best_match:  # First partial match
                            best_match = str(channel.id)
                            
                if exact_match:  # Break out of outer loop if exact match found
                    break
        
        return exact_match or best_match
    
    async def _resolve_server_id(self, server_name: str) -> Optional[str]:
        """Resolve server name to server ID"""
        if not server_name:
            return None
            
        server_name_lower = server_name.lower().strip()
        best_match = None
        exact_match = None
        
        # Search through all accessible guilds
        for guild in self.bot.guilds:
            # Exact name match (case-insensitive)
            if guild.name.lower() == server_name_lower:
                exact_match = str(guild.id)
                break
            # Partial matches for fallback
            if server_name_lower in guild.name.lower():
                if not best_match:  # First partial match
                    best_match = str(guild.id)
        
        return exact_match or best_match
    
    def _should_include_message(self, message: discord.Message, query: Optional[str], 
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
            
        # If no query provided, include all messages that pass other filters
        if not query:
            return True
            
        # Content search - skip empty messages when searching
        content = message.content
        if not content:  # Skip empty messages when doing content search
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
                "name": getattr(message.channel, 'name', None),
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
    
    async def _search_channel(self, channel: Union[discord.TextChannel, discord.DMChannel], query: Optional[str],
                             limit: int, case_sensitive: bool, exclude_bots: bool,
                             author_id: Optional[str], cutoff_time: Optional[datetime],
                             max_results: int) -> List[Dict[str, Any]]:
        """Search through a specific channel"""
        results = []
        messages_searched = 0
        matching_author_count = 0

        # Get channel name before try block so it's available in exception handlers
        channel_name = getattr(channel, 'name', None) or f'DM-{channel.id}'

        try:
            async for message in channel.history(limit=limit):
                messages_searched += 1

                # Debug logging for specific channel and author
                if channel_name == "based-text-chat" and author_id and str(message.author.id) == author_id:
                    matching_author_count += 1
                    if query and query.lower() in message.content.lower():
                        logger.info(f"DEBUG: Found matching message in {channel_name} from target user: '{message.content[:100]}...'")
                    elif query:
                        logger.info(f"DEBUG: Found message from target user in {channel_name} but no query match: '{message.content[:100]}...'")
                
                if self._should_include_message(message, query, case_sensitive, 
                                               exclude_bots, author_id, cutoff_time):
                    results.append(self._format_message_result(message))
                    
                    # Stop if we have enough results
                    if len(results) >= max_results:
                        break
                
                # Rate limiting
                if messages_searched % 100 == 0:
                    await asyncio.sleep(self.rate_limit_delay)
                    
            # Debug logging for based-text-chat
            if channel_name == "based-text-chat" and author_id:
                logger.info(f"DEBUG: In {channel_name} searched {messages_searched} messages, found {matching_author_count} from target user, {len(results)} final results")
                    
        except discord.Forbidden as e:
            logger.warning(f"Bot lacks permission to read history in channel '{channel_name}': {e}")
        except Exception as e:
            logger.error(f"Error searching channel '{channel_name}': {e}")
            
        return results
    
    async def execute(self, query: Optional[str] = None, channel_id: Optional[str] = None,
                     server_id: Optional[str] = None, limit: int = 10000,
                     author_id: Optional[str] = None, author_name: Optional[str] = None,
                     channel_name: Optional[str] = None, server_name: Optional[str] = None,
                     time_range: Optional[str] = None, case_sensitive: bool = False, 
                     exclude_bots: bool = True, max_results: int = 20,
                     requesting_user_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute Discord message search"""
        try:
            # Validate parameters - require either query or author filter
            if query and len(query.strip()) < 2:
                return {
                    "success": False,
                    "error": "Query must be at least 2 characters long"
                }
            
            if not query and not author_name and not author_id:
                return {
                    "success": False,
                    "error": "Either a search query or author filter (author_name/author_id) must be provided"
                }
            
            # Resolve server_name to server_id if provided
            resolved_server_id = None
            if server_name and not server_id:
                resolved_server_id = await self._resolve_server_id(server_name)
                if not resolved_server_id:
                    return {
                        "success": False,
                        "error": f"Could not find server with name '{server_name}'. Try using the exact server name."
                    }
            
            # Use resolved server_id or provided server_id
            final_server_id = server_id or resolved_server_id
            
            # Resolve channel_name to channel_id if provided
            resolved_channel_id = None
            if channel_name and not channel_id:
                # Determine guild context for channel resolution
                guild_id = None
                if final_server_id:
                    guild_id = int(final_server_id)
                
                resolved_channel_id = await self._resolve_channel_id(channel_name, guild_id)
                if not resolved_channel_id:
                    return {
                        "success": False,
                        "error": f"Could not find channel with name '{channel_name}'. Try using the exact channel name."
                    }
            
            # Use resolved channel_id or provided channel_id  
            final_channel_id = channel_id or resolved_channel_id
            
            # Resolve author_name to author_id if provided
            resolved_author_id = None
            if author_name and not author_id:
                # Determine guild context for user resolution
                guild_id = None
                if final_server_id:
                    guild_id = int(final_server_id)
                elif final_channel_id:
                    channel = self.bot.get_channel(int(final_channel_id))
                    if channel and channel.guild:
                        guild_id = channel.guild.id
                
                resolved_author_id = await self._resolve_user_id(author_name, guild_id)
                if not resolved_author_id:
                    return {
                        "success": False,
                        "error": f"Could not find user with name '{author_name}'. Try using the exact username or display name."
                    }
            
            # Use resolved author_id or provided author_id
            final_author_id = author_id or resolved_author_id
            
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
            if final_channel_id:
                channel = self.bot.get_channel(int(final_channel_id))
                if not channel:
                    return {
                        "success": False,
                        "error": f"Channel with ID {final_channel_id} not found or not accessible"
                    }
                
                if not isinstance(channel, (discord.TextChannel, discord.DMChannel)):
                    return {
                        "success": False,
                        "error": f"Channel {final_channel_id} is not a text channel or DM channel"
                    }
                
                # Security check: Verify requesting user has access to this channel
                if requesting_user_id:
                    if isinstance(channel, discord.TextChannel) and channel.guild:
                        member = channel.guild.get_member(int(requesting_user_id))
                        if not member:
                            return {
                                "success": False,
                                "error": f"You are not a member of the server containing channel {final_channel_id}"
                            }
                        
                        # Check channel permissions
                        perms = channel.permissions_for(member)
                        if not perms.read_messages:
                            return {
                                "success": False,
                                "error": f"You do not have permission to read messages in channel {getattr(channel, 'name', f'DM-{channel.id}')}"
                            }
                    elif isinstance(channel, discord.DMChannel):
                        # Security check for DM channels: user can only search their own DMs
                        if str(channel.recipient.id) != requesting_user_id:
                            return {
                                "success": False,
                                "error": "You can only search your own DM messages"
                            }
                
                channel_results = await self._search_channel(
                    channel, query, limit, case_sensitive, exclude_bots,
                    final_author_id, cutoff_time, max_results
                )
                results.extend(channel_results)
                channel_display_name = getattr(channel, 'name', f'DM-{channel.id}') if isinstance(channel, discord.TextChannel) else f'DM-{channel.id}'
                channels_searched.append(channel_display_name)
                search_stats["channels_searched"] = 1
                
            # Search specific server
            elif final_server_id:
                guild = self.bot.get_guild(int(final_server_id))
                if not guild:
                    return {
                        "success": False,
                        "error": f"Server with ID {final_server_id} not found or not accessible"
                    }
                
                # Security check: Verify requesting user is a member of this server
                if requesting_user_id:
                    member = guild.get_member(int(requesting_user_id))
                    if not member:
                        return {
                            "success": False,
                            "error": f"You are not a member of server '{guild.name}'"
                        }
                
                for channel in guild.text_channels:
                    if len(results) >= max_results:
                        break
                    
                    # Skip channels the requesting user can't access
                    if requesting_user_id and member:
                        perms = channel.permissions_for(member)
                        if not perms.read_messages:
                            search_stats["permission_errors"] += 1
                            logger.info(f"Skipping channel '{channel.name}' - user lacks read permission")
                            continue
                        
                    try:
                        channel_results = await self._search_channel(
                            channel, query, limit // len(guild.text_channels) + 1,
                            case_sensitive, exclude_bots, final_author_id, cutoff_time,
                            max_results - len(results)
                        )
                        results.extend(channel_results)
                        channels_searched.append(channel.name)
                        search_stats["channels_searched"] += 1
                        
                    except discord.Forbidden:
                        search_stats["permission_errors"] += 1
                        logger.warning(f"Permission denied for channel '{channel.name}' in '{guild.name}'")
                    
                    # Rate limiting between channels
                    await asyncio.sleep(self.rate_limit_delay)
            
            # Search all accessible servers (limited scope for performance)
            else:
                # Security: Only search servers where the requesting user is a member
                if requesting_user_id:
                    # Get only guilds where the user is a member
                    user_guilds = []
                    for guild in self.bot.guilds:
                        member = guild.get_member(int(requesting_user_id))
                        if member:
                            user_guilds.append(guild)
                    
                    # Limit to first few guilds to prevent excessive API usage
                    guilds_to_search = user_guilds[:3]  # Max 3 servers
                else:
                    # Fallback if no requesting_user_id (shouldn't happen in production)
                    guilds_to_search = list(self.bot.guilds)[:3]
                
                for guild in guilds_to_search:
                    if len(results) >= max_results:
                        break
                    
                    # Get member for permission checks
                    member = guild.get_member(int(requesting_user_id)) if requesting_user_id else None
                        
                    # Limit channels per guild
                    channels_to_search = guild.text_channels[:5]  # Max 5 channels per server
                    
                    for channel in channels_to_search:
                        if len(results) >= max_results:
                            break
                        
                        # Skip channels the requesting user can't access
                        if requesting_user_id and member:
                            perms = channel.permissions_for(member)
                            if not perms.read_messages:
                                logger.info(f"Skipping channel '{channel.name}' in '{guild.name}' - user lacks read permission")
                                continue
                            
                        try:
                            channel_results = await self._search_channel(
                                channel, query, min(limit // 10, 100),  # Reduced limit for broad search
                                case_sensitive, exclude_bots, final_author_id, cutoff_time,
                                max_results - len(results)
                            )
                            results.extend(channel_results)
                            channels_searched.append(f"{guild.name}#{channel.name}")
                            search_stats["channels_searched"] += 1
                            
                        except discord.Forbidden:
                            search_stats["permission_errors"] += 1
                            logger.warning(f"Permission denied for channel '{channel.name}' in '{guild.name}'")
                        
                        # Rate limiting
                        await asyncio.sleep(self.rate_limit_delay)
            
            elapsed_time = time.time() - start_time
            
            # Sort results by timestamp (newest first)
            results.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Build search description message
            if query:
                search_description = f'matching "{query}"'
            else:
                search_description = "from specified user"
            
            # Log comprehensive search summary
            logger.info(f"Discord message search completed:")
            logger.info(f"  Query: '{query}' | Author: {author_name or final_author_id or 'Any'}")
            logger.info(f"  Server: {server_name or final_server_id or 'Multiple'} | Channel: {channel_name or final_channel_id or 'Multiple'}")
            logger.info(f"  Time range: {time_range or 'All time'} | Results: {len(results)}/{max_results}")
            logger.info(f"  Channels searched: {search_stats['channels_searched']} | Permission errors: {search_stats['permission_errors']}")
            logger.info(f"  Searched channels: {', '.join(channels_searched[:10])}")  # Log first 10 channel names
            logger.info(f"  Search time: {round(elapsed_time, 2)}s")
            
            # Warn if high permission error rate
            if search_stats['channels_searched'] > 0:
                error_rate = search_stats['permission_errors'] / (search_stats['channels_searched'] + search_stats['permission_errors'])
                if error_rate > 0.5:
                    logger.warning(f"High permission error rate ({error_rate:.0%}) - many channels inaccessible to user")
            elif search_stats['permission_errors'] > 0:
                logger.warning(f"All {search_stats['permission_errors']} channels were inaccessible - no channels could be searched")
            
            # Add warning to message if permission errors occurred
            warning_suffix = ""
            if search_stats['permission_errors'] > 0:
                warning_suffix = f" (Note: {search_stats['permission_errors']} channels were inaccessible)"
            
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
                    "author_id": final_author_id,
                    "author_name_searched": author_name,
                    "time_range": time_range,
                    "cutoff_time": cutoff_time.isoformat() if cutoff_time else None
                },
                "message": f"Found {len(results)} message(s) {search_description} across {search_stats['channels_searched']} channel(s){warning_suffix}"
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