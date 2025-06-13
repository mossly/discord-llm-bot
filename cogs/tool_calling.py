"""
Tool calling cog for managing tool execution in chat
"""

import discord
from discord.ext import commands
import logging
import json
from typing import List, Dict, Any, Optional
from .tools import ToolRegistry, WebSearchTool, ContentRetrievalTool, DeepResearchTool, ConversationSearchTool, DiscordMessageSearchTool, ContextAwareDiscordSearchTool, DiscordUserLookupTool, ReminderTool

logger = logging.getLogger(__name__)


class ToolCalling(commands.Cog):
    """Cog for managing tool calling functionality"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.registry = ToolRegistry()
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize default tools"""
        # Web search tool
        web_search = WebSearchTool(use_ddg=True)
        self.registry.register(web_search, enabled=True)
        
        # Content retrieval tool
        content_tool = ContentRetrievalTool()
        self.registry.register(content_tool, enabled=True)
        
        # Deep research tool
        deep_research = DeepResearchTool(bot=self.bot)
        self.registry.register(deep_research, enabled=True)
        
        # Conversation search tool
        conversation_search = ConversationSearchTool()
        self.registry.register(conversation_search, enabled=True)
        
        # Discord message search tool
        discord_search = DiscordMessageSearchTool(bot=self.bot)
        self.registry.register(discord_search, enabled=True)
        
        # Context-aware Discord message search tool
        context_discord_search = ContextAwareDiscordSearchTool(bot=self.bot)
        self.registry.register(context_discord_search, enabled=True)
        
        # Discord user lookup tool
        discord_user_lookup = DiscordUserLookupTool(bot=self.bot)
        self.registry.register(discord_user_lookup, enabled=True)
        
        # Reminder management tool
        reminder_tool = ReminderTool()
        self.registry.register(reminder_tool, enabled=True)
        
        logger.info(f"Initialized {len(self.registry.list_tools())} tools")
    
    def get_registry(self) -> ToolRegistry:
        """Get the tool registry"""
        return self.registry
    
    def set_discord_context(self, channel: discord.TextChannel):
        """Set Discord context for context-aware tools"""
        # Find the context-aware Discord search tool and set its context
        for tool_name in self.registry.list_tools():
            tool_instance = self.registry.get(tool_name)
            if tool_instance and hasattr(tool_instance, 'set_context'):
                tool_instance.set_context(channel)
                if channel and channel.guild:
                    channel_name = getattr(channel, 'name', f'Channel {channel.id}')
                    logger.info(f"Set Discord context for {tool_instance.name}: {channel.guild.name}#{channel_name}")
                elif channel:
                    logger.info(f"Set Discord context for {tool_instance.name}: DM channel {channel.id}")
                else:
                    logger.info(f"Set Discord context for {tool_instance.name}: None channel")
    
    async def process_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        user_id: str,
        channel: discord.TextChannel,
        session_id: str = None,
        model: str = None,
        requesting_user_id: str = None
    ) -> List[Dict[str, Any]]:
        """Process a list of tool calls and return results"""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name")
            tool_id = tool_call.get("id")
            
            if not tool_name:
                results.append({
                    "tool_call_id": tool_id,
                    "error": "No tool name provided"
                })
                continue
            
            # Parse arguments
            try:
                arguments = tool_call.get("function", {}).get("arguments", "{}")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
            except json.JSONDecodeError as e:
                results.append({
                    "tool_call_id": tool_id,
                    "error": f"Invalid arguments JSON: {e}"
                })
                continue
            
            # Execute tool
            logger.info(f"Executing tool '{tool_name}' for user {user_id}")
            logger.info(f"Executing tool '{tool_name}' with parameters: {arguments}")
            
            # Pass model parameter for deep_research tool
            if tool_name == "deep_research" and model:
                arguments["model"] = model
            
            # Auto-inject user_id for search_conversations tool and enforce security
            if tool_name == "search_conversations":
                # Force the user_id to match the requesting user for security
                arguments["user_id"] = requesting_user_id or user_id
            
            # Pass requesting_user_id for security validation in search tools
            if tool_name in ["search_discord_messages", "search_current_discord_messages"]:
                arguments["requesting_user_id"] = requesting_user_id or user_id
            
            # Auto-inject user_id for manage_reminders tool and enforce security
            if tool_name == "manage_reminders":
                # Force the user_id to match the requesting user for security
                arguments["user_id"] = requesting_user_id or user_id
            
            result = await self.registry.execute_tool(tool_name, session_id=session_id, **arguments)
            
            # Enhanced logging for search tools
            if tool_name in ["search_discord_messages", "search_current_discord_messages", "search_conversations"]:
                # Log search parameters
                search_params = {
                    "tool": tool_name,
                    "query": arguments.get("query", ""),
                    "user_id": arguments.get("user_id", ""),
                    "author_name": arguments.get("author_name", ""),
                    "server_id": arguments.get("server_id", ""),
                    "server_name": arguments.get("server_name", ""),
                    "channel_id": arguments.get("channel_id", ""),
                    "channel_name": arguments.get("channel_name", ""),
                    "time_range": arguments.get("time_range", ""),
                    "results_found": len(result.get('results', []))
                }
                logger.info(f"Search executed: {search_params}")
                
                # Log truncated results for debugging
                if result.get('results'):
                    first_results = result['results'][:3]  # First 3 results
                    for i, res in enumerate(first_results):
                        if tool_name == "search_conversations":
                            preview = f"User: {res.get('user_message', '')[:50]}... Bot: {res.get('bot_response', '')[:50]}..."
                        else:  # Discord message search
                            preview = f"{res.get('author', {}).get('name', 'Unknown')}: {res.get('content', '')[:100]}..."
                        logger.info(f"  Result {i+1}: {preview}")
                    
                    if len(result['results']) > 3:
                        logger.info(f"  ... and {len(result['results']) - 3} more results")
            else:
                logger.info(f"Tool '{tool_name}' executed successfully, found {len(result.get('results', []))} results")
            
            # Format result
            results.append({
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "result": result
            })
            
            # Log to channel if in debug mode
            if hasattr(self.bot, 'debug_mode') and self.bot.debug_mode:
                embed = discord.Embed(
                    title=f"Tool Executed: {tool_name}",
                    description=f"Arguments: {json.dumps(arguments, indent=2)}",
                    color=0x00FF00 if result.get("success") else 0xFF0000
                )
                await channel.send(embed=embed)
        
        return results
    
    def format_tool_results_for_llm(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tool results for LLM consumption"""
        formatted_results = []
        
        for result in results:
            tool_name = result.get("tool_name")
            tool_result = result.get("result", {})
            
            # Get the tool to format its own results
            tool = self.registry.get(tool_name)
            if tool and hasattr(tool, 'format_results_for_llm'):
                content = tool.format_results_for_llm(tool_result)
            else:
                # Default formatting
                if tool_result.get("success"):
                    content = json.dumps(tool_result, indent=2)
                else:
                    content = f"Tool error: {tool_result.get('error', 'Unknown error')}"
            
            formatted_results.append({
                "role": "tool",
                "tool_call_id": result.get("tool_call_id"),
                "content": content
            })
        
        return formatted_results
    
    def start_session(self, session_id: str) -> None:
        """Start a new tool usage session"""
        self.registry.start_session(session_id)
    
    def end_session(self, session_id: str) -> None:
        """End a tool usage session"""
        self.registry.end_session(session_id)
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get tool usage statistics for a session"""
        return self.registry.get_session_stats(session_id)
    
    def get_session_usage_totals(self, session_id: str) -> Dict[str, Any]:
        """Get aggregated usage statistics from all tools in the session"""
        return self.registry.get_session_usage_totals(session_id)
    
    @commands.command(name="tools")
    @commands.is_owner()
    async def list_tools(self, ctx: commands.Context):
        """List all available tools and their status"""
        stats = self.registry.get_stats()
        
        embed = discord.Embed(
            title="Available Tools",
            description="Tool usage statistics",
            color=0x00FF00
        )
        
        for tool_name, tool_stats in stats.items():
            status = "✅ Enabled" if tool_stats["enabled"] else "❌ Disabled"
            embed.add_field(
                name=tool_name,
                value=f"{status}\nUsed: {tool_stats['usage_count']}\nErrors: {tool_stats['error_count']}",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="toggle_tool")
    @commands.is_owner()
    async def toggle_tool(self, ctx: commands.Context, tool_name: str):
        """Enable or disable a tool"""
        if self.registry.is_enabled(tool_name):
            success = self.registry.disable(tool_name)
            action = "disabled"
        else:
            success = self.registry.enable(tool_name)
            action = "enabled"
        
        if success:
            await ctx.send(f"Tool '{tool_name}' has been {action}.")
        else:
            await ctx.send(f"Tool '{tool_name}' not found.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ToolCalling(bot))