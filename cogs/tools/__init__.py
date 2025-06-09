"""
Tool system for Discord LLM Bot
"""

from .base_tool import BaseTool
from .tool_registry import ToolRegistry

# Import tools conditionally to handle missing dependencies
try:
    from .web_search_tool import WebSearchTool
    WEB_SEARCH_AVAILABLE = True
except ImportError:
    WEB_SEARCH_AVAILABLE = False
    WebSearchTool = None

try:
    from .content_tool import ContentRetrievalTool
    CONTENT_TOOL_AVAILABLE = True
except ImportError:
    CONTENT_TOOL_AVAILABLE = False
    ContentRetrievalTool = None

__all__ = ['BaseTool', 'ToolRegistry']

if WEB_SEARCH_AVAILABLE:
    __all__.append('WebSearchTool')

if CONTENT_TOOL_AVAILABLE:
    __all__.append('ContentRetrievalTool')