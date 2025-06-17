"""
Data classes for chat request/response parameters
Simplifies function signatures and improves maintainability
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import discord
from discord import Interaction


@dataclass
class APIConfig:
    """Configuration for API client settings"""
    api: str = "openai"  # "openai" or "openrouter"
    model: str = "gemini-2.5-flash-preview"
    max_tokens: int = 8000
    
    def __post_init__(self):
        """Validate API configuration"""
        if self.api not in ["openai", "openrouter"]:
            raise ValueError(f"Invalid API: {self.api}. Must be 'openai' or 'openrouter'")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


@dataclass 
class ToolConfig:
    """Configuration for tool calling behavior"""
    use_tools: bool = True
    force_tools: bool = False
    allowed_tools: Optional[List[str]] = None
    max_iterations: int = 10
    deep_research: bool = False
    
    def __post_init__(self):
        """Validate tool configuration"""
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")


@dataclass
class ChatRequest:
    """Complete chat request parameters bundled into a single object"""
    # Core required parameters
    prompt: str
    user_id: str
    channel: discord.TextChannel
    
    # API configuration
    api_config: APIConfig = field(default_factory=APIConfig)
    
    # Tool configuration  
    tool_config: ToolConfig = field(default_factory=ToolConfig)
    
    # Optional content parameters
    image_url: Optional[str] = None
    reference_message: Optional[str] = None
    attachments: Optional[List[discord.Attachment]] = None
    
    # Behavior flags
    use_fun: bool = False
    web_search: bool = False
    
    # Discord context
    interaction: Optional[Interaction] = None
    username: Optional[str] = None
    
    # Response formatting
    reply_footer: Optional[str] = None
    create_thread: bool = False
    
    def __post_init__(self):
        """Validate chat request parameters"""
        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.channel:
            raise ValueError("channel is required")


@dataclass
class ChatResponse:
    """Standardized chat response with metadata"""
    content: str
    elapsed_time: float
    footer: str
    
    # Optional metadata
    token_usage: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    cost: Optional[float] = None
    model_used: Optional[str] = None
    
    def __post_init__(self):
        """Validate response data"""
        if self.elapsed_time < 0:
            raise ValueError("elapsed_time cannot be negative")


class ChatRequestBuilder:
    """Builder pattern for creating ChatRequest objects with defaults"""
    
    def __init__(self, prompt: str, user_id: str, channel: discord.TextChannel):
        self._request = ChatRequest(
            prompt=prompt,
            user_id=user_id, 
            channel=channel
        )
    
    def with_model(self, model: str) -> 'ChatRequestBuilder':
        """Set the AI model to use"""
        self._request.api_config.model = model
        return self
    
    def with_api(self, api: str) -> 'ChatRequestBuilder':
        """Set the API to use (openai/openrouter)"""
        self._request.api_config.api = api
        return self
    
    def with_max_tokens(self, max_tokens: int) -> 'ChatRequestBuilder':
        """Set maximum tokens for response"""
        self._request.api_config.max_tokens = max_tokens
        return self
    
    def with_tools(self, use_tools: bool = True, allowed_tools: Optional[List[str]] = None) -> 'ChatRequestBuilder':
        """Configure tool usage"""
        self._request.tool_config.use_tools = use_tools
        self._request.tool_config.allowed_tools = allowed_tools
        return self
    
    def with_image(self, image_url: str) -> 'ChatRequestBuilder':
        """Add image to the request"""
        self._request.image_url = image_url
        return self
    
    def with_reference(self, reference_message: str) -> 'ChatRequestBuilder':
        """Add reference message for context"""
        self._request.reference_message = reference_message
        return self
    
    def with_interaction(self, interaction: Interaction, username: Optional[str] = None) -> 'ChatRequestBuilder':
        """Add Discord interaction context"""
        self._request.interaction = interaction
        self._request.username = username or interaction.user.name
        return self
    
    def with_fun_mode(self, use_fun: bool = True) -> 'ChatRequestBuilder':
        """Enable fun mode responses"""
        self._request.use_fun = use_fun
        return self
    
    def with_web_search(self, web_search: bool = True) -> 'ChatRequestBuilder':
        """Enable web search capability"""
        self._request.web_search = web_search
        return self
    
    def with_deep_research(self, deep_research: bool = True) -> 'ChatRequestBuilder':
        """Enable deep research mode"""
        self._request.tool_config.deep_research = deep_research
        return self
    
    def with_footer(self, footer: str) -> 'ChatRequestBuilder':
        """Set custom reply footer"""
        self._request.reply_footer = footer
        return self
    
    def build(self) -> ChatRequest:
        """Build the final ChatRequest object"""
        return self._request


# Factory functions for common request patterns
def create_simple_request(prompt: str, user_id: str, channel: discord.TextChannel, 
                         model: str = "gemini-2.5-flash-preview") -> ChatRequest:
    """Create a simple chat request with minimal configuration"""
    return ChatRequestBuilder(prompt, user_id, channel).with_model(model).build()


def create_tool_request(prompt: str, user_id: str, channel: discord.TextChannel,
                       allowed_tools: Optional[List[str]] = None,
                       model: str = "gemini-2.5-flash-preview") -> ChatRequest:
    """Create a chat request with tool calling enabled"""
    return (ChatRequestBuilder(prompt, user_id, channel)
            .with_model(model)
            .with_tools(use_tools=True, allowed_tools=allowed_tools)
            .build())


def create_interaction_request(prompt: str, interaction: Interaction,
                              model: str = "gemini-2.5-flash-preview") -> ChatRequest:
    """Create a chat request from a Discord interaction"""
    return (ChatRequestBuilder(prompt, str(interaction.user.id), interaction.channel)
            .with_model(model)
            .with_interaction(interaction)
            .build())


# Export all classes and functions
__all__ = [
    'APIConfig',
    'ToolConfig', 
    'ChatRequest',
    'ChatResponse',
    'ChatRequestBuilder',
    'create_simple_request',
    'create_tool_request', 
    'create_interaction_request'
]