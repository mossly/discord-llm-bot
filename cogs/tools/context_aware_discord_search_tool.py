"""
Context-aware Discord message search tool that automatically uses current server/channel context
"""

from typing import Dict, Any, Optional
from .discord_message_search_tool import DiscordMessageSearchTool
import discord
import logging

logger = logging.getLogger(__name__)


class ContextAwareDiscordSearchTool(DiscordMessageSearchTool):
    """Context-aware version of Discord message search that uses current server/channel as defaults"""
    
    def __init__(self, bot: discord.Client):
        super().__init__(bot)
        self.current_channel = None
        self.current_guild = None
    
    @property
    def name(self) -> str:
        return "search_current_discord_messages"
    
    @property
    def description(self) -> str:
        return "Search through Discord message history in the current server context. Can search by content query, by user, or both. By default searches the entire current server. Can be narrowed to specific channels using channel_id, or search different servers with server_id. Note: You can only search messages in servers and channels where you have access."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        # Inherit base parameters but modify descriptions to indicate context awareness
        base_params = super().parameters.copy()
        
        # Update descriptions to indicate context-aware behavior
        base_params["properties"]["channel_id"]["description"] = "Specific channel ID to search in (optional). If not provided, searches all accessible channels in the current server."
        base_params["properties"]["server_id"]["description"] = "Specific server/guild ID to search in (optional). If not provided, uses the current server context."
        
        return base_params
    
    def set_context(self, channel: discord.TextChannel):
        """Set the current Discord context for this tool"""
        self.current_channel = channel
        self.current_guild = channel.guild if channel else None
        logger.info(f"Discord search context set to: {channel.guild.name}#{channel.name} (Server: {channel.guild.id}, Channel: {channel.id})")
    
    async def execute(self, query: Optional[str] = None, channel_id: Optional[str] = None,
                     server_id: Optional[str] = None, limit: int = 10000,
                     author_id: Optional[str] = None, author_name: Optional[str] = None,
                     channel_name: Optional[str] = None, server_name: Optional[str] = None,
                     time_range: Optional[str] = None, case_sensitive: bool = False, 
                     exclude_bots: bool = True, max_results: int = 20,
                     requesting_user_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute context-aware Discord message search"""
        
        # Use current context as defaults if no specific IDs provided
        effective_channel_id = channel_id
        effective_server_id = server_id
        
        # If no server specified, use current server context (search whole server by default)
        if not effective_server_id and self.current_guild:
            effective_server_id = str(self.current_guild.id)
            logger.info(f"Using current server context: {self.current_guild.name} ({effective_server_id})")
        
        # Only use channel context if explicitly requested or if no server context
        # This allows searching the whole server by default while still allowing specific channel searches
        if channel_id:
            effective_channel_id = channel_id
            logger.info(f"Using specified channel: {effective_channel_id}")
        elif not effective_server_id and self.current_channel:
            # Fallback: if somehow we have no server context, at least use channel
            effective_channel_id = str(self.current_channel.id)
            logger.info(f"Using current channel as fallback: {self.current_channel.name} ({effective_channel_id})")
        
        # Call the parent class execute method with the effective IDs and security context
        result = await super().execute(
            query=query,
            channel_id=effective_channel_id,
            server_id=effective_server_id,
            limit=limit,
            author_id=author_id,
            author_name=author_name,
            channel_name=channel_name,
            server_name=server_name,
            time_range=time_range,
            case_sensitive=case_sensitive,
            exclude_bots=exclude_bots,
            max_results=max_results,
            requesting_user_id=requesting_user_id
        )
        
        # Add context information to the result
        if result.get("success"):
            result["context_used"] = {
                "current_channel": {
                    "id": str(self.current_channel.id) if self.current_channel else None,
                    "name": self.current_channel.name if self.current_channel else None
                },
                "current_server": {
                    "id": str(self.current_guild.id) if self.current_guild else None,
                    "name": self.current_guild.name if self.current_guild else None
                },
                "effective_channel_id": effective_channel_id,
                "effective_server_id": effective_server_id,
                "used_context_defaults": not (channel_id or server_id)
            }
        
        return result
    
    def get_usage_summary(self) -> str:
        """Get a summary of tool usage for monitoring"""
        context_info = ""
        if self.current_channel:
            context_info = f" (Context: {self.current_guild.name}#{self.current_channel.name})"
        return f"ContextAwareDiscordSearch: {self.usage_count} searches, {self.error_count} errors{context_info}"