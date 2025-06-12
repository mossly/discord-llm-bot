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

try:
    from .discord_message_search_tool import DiscordMessageSearchTool
    DISCORD_MESSAGE_SEARCH_AVAILABLE = True
except ImportError:
    DISCORD_MESSAGE_SEARCH_AVAILABLE = False
    DiscordMessageSearchTool = None

try:
    from .context_aware_discord_search_tool import ContextAwareDiscordSearchTool
    CONTEXT_AWARE_DISCORD_SEARCH_AVAILABLE = True
except ImportError:
    CONTEXT_AWARE_DISCORD_SEARCH_AVAILABLE = False
    ContextAwareDiscordSearchTool = None

try:
    from .discord_user_lookup_tool import DiscordUserLookupTool
    DISCORD_USER_LOOKUP_AVAILABLE = True
except ImportError:
    DISCORD_USER_LOOKUP_AVAILABLE = False
    DiscordUserLookupTool = None

__all__ = ['BaseTool', 'ToolRegistry']

if WEB_SEARCH_AVAILABLE:
    __all__.append('WebSearchTool')

if CONTENT_TOOL_AVAILABLE:
    __all__.append('ContentRetrievalTool')

if DEEP_RESEARCH_AVAILABLE:
    __all__.append('DeepResearchTool')

if CONVERSATION_SEARCH_AVAILABLE:
    __all__.append('ConversationSearchTool')

if DISCORD_MESSAGE_SEARCH_AVAILABLE:
    __all__.append('DiscordMessageSearchTool')

if CONTEXT_AWARE_DISCORD_SEARCH_AVAILABLE:
    __all__.append('ContextAwareDiscordSearchTool')

if DISCORD_USER_LOOKUP_AVAILABLE:
    __all__.append('DiscordUserLookupTool')