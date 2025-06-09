"""
Tool registry for managing available tools
"""

from typing import Dict, List, Optional, Any
from .base_tool import BaseTool
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing tools"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._enabled_tools: set = set()
        self._session_usage: Dict[str, Dict[str, int]] = {}  # session_id -> {tool_name: usage_count}
        self._session_start_times: Dict[str, float] = {}  # session_id -> start_time
    
    def register(self, tool: BaseTool, enabled: bool = True) -> None:
        """Register a tool"""
        if not isinstance(tool, BaseTool):
            raise ValueError(f"Tool must be an instance of BaseTool, got {type(tool)}")
        
        self._tools[tool.name] = tool
        if enabled:
            self._enabled_tools.add(tool.name)
        
        logger.info(f"Registered tool '{tool.name}' (enabled={enabled})")
    
    def unregister(self, tool_name: str) -> None:
        """Unregister a tool"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._enabled_tools.discard(tool_name)
            logger.info(f"Unregistered tool '{tool_name}'")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(name)
    
    def get_enabled(self, name: str) -> Optional[BaseTool]:
        """Get tool by name only if enabled"""
        if name in self._enabled_tools:
            return self._tools.get(name)
        return None
    
    def enable(self, tool_name: str) -> bool:
        """Enable a tool"""
        if tool_name in self._tools:
            self._enabled_tools.add(tool_name)
            logger.info(f"Enabled tool '{tool_name}'")
            return True
        return False
    
    def disable(self, tool_name: str) -> bool:
        """Disable a tool"""
        if tool_name in self._enabled_tools:
            self._enabled_tools.remove(tool_name)
            logger.info(f"Disabled tool '{tool_name}'")
            return True
        return False
    
    def is_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled"""
        return tool_name in self._enabled_tools
    
    def list_tools(self, enabled_only: bool = True) -> List[str]:
        """List all registered tool names"""
        if enabled_only:
            return list(self._enabled_tools)
        return list(self._tools.keys())
    
    def get_all_schemas(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get OpenAI-format tool schemas"""
        tools = []
        for name, tool in self._tools.items():
            if not enabled_only or name in self._enabled_tools:
                tools.append(tool.get_openai_schema())
        return tools
    
    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Get usage statistics for all tools"""
        stats = {}
        for name, tool in self._tools.items():
            stats[name] = {
                "usage_count": tool.usage_count,
                "error_count": tool.error_count,
                "enabled": name in self._enabled_tools
            }
        return stats
    
    async def execute_tool(self, tool_name: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name with optional session tracking"""
        tool = self.get_enabled(tool_name)
        if not tool:
            return {
                "error": f"Tool '{tool_name}' not found or not enabled",
                "success": False
            }
        
        # Validate parameters
        validation_error = tool.validate_parameters(**kwargs)
        if validation_error:
            return {
                "error": validation_error,
                "success": False
            }
        
        # Track session usage if session_id provided
        if session_id:
            self._track_session_usage(session_id, tool_name)
        
        # Execute tool
        return await tool(**kwargs)
    
    def start_session(self, session_id: str) -> None:
        """Start a new tool usage session"""
        self._session_usage[session_id] = defaultdict(int)
        self._session_start_times[session_id] = time.time()
        # Reset all tool session stats
        for tool in self._tools.values():
            tool.reset_session_stats()
        logger.debug(f"Started tool session: {session_id}")
    
    def end_session(self, session_id: str) -> None:
        """End a tool usage session and clean up"""
        if session_id in self._session_usage:
            del self._session_usage[session_id]
        if session_id in self._session_start_times:
            del self._session_start_times[session_id]
        logger.debug(f"Ended tool session: {session_id}")
    
    def _track_session_usage(self, session_id: str, tool_name: str) -> None:
        """Track tool usage for a session"""
        if session_id not in self._session_usage:
            self.start_session(session_id)
        self._session_usage[session_id][tool_name] += 1
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get tool usage statistics for a specific session"""
        if session_id not in self._session_usage:
            return {
                "tools_used": {},
                "total_tool_calls": 0,
                "session_duration": 0,
                "active": False
            }
        
        usage = dict(self._session_usage[session_id])
        total_calls = sum(usage.values())
        duration = time.time() - self._session_start_times.get(session_id, time.time())
        
        return {
            "tools_used": usage,
            "total_tool_calls": total_calls,
            "session_duration": duration,
            "active": True
        }
    
    def get_session_usage_totals(self, session_id: str) -> Dict[str, Any]:
        """Get aggregated usage statistics from all tools in the session"""
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        
        for tool in self._tools.values():
            stats = tool.session_stats
            total_input_tokens += stats["input_tokens"]
            total_output_tokens += stats["output_tokens"]
            total_cost += stats["cost"]
        
        return {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cost": total_cost
        }