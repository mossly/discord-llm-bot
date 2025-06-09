"""
Tool registry for managing available tools
"""

from typing import Dict, List, Optional, Any
from .base_tool import BaseTool
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing tools"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._enabled_tools: set = set()
    
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
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name"""
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
        
        # Execute tool
        return await tool(**kwargs)