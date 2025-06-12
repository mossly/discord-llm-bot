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

try:
    from .deep_research_tool import DeepResearchTool
    DEEP_RESEARCH_AVAILABLE = True
except ImportError:
    DEEP_RESEARCH_AVAILABLE = False
    DeepResearchTool = None

try:
    from .conversation_search_tool import ConversationSearchTool
    CONVERSATION_SEARCH_AVAILABLE = True
except ImportError:
    CONVERSATION_SEARCH_AVAILABLE = False
    ConversationSearchTool = None

__all__ = ['BaseTool', 'ToolRegistry']

if WEB_SEARCH_AVAILABLE:
    __all__.append('WebSearchTool')

if CONTENT_TOOL_AVAILABLE:
    __all__.append('ContentRetrievalTool')

if DEEP_RESEARCH_AVAILABLE:
    __all__.append('DeepResearchTool')

if CONVERSATION_SEARCH_AVAILABLE:
    __all__.append('ConversationSearchTool')