# Tool Calling Integration Plan for Discord LLM Bot

## Overview
This document outlines the implementation plan for integrating tool calling capabilities into the Discord LLM bot, inspired by the moss-deep-research project. The integration will enable the bot to recursively call tools (web search, content retrieval) before generating responses.

## Architecture Design

### 1. Core Components

#### 1.1 Tool System Architecture
```
cogs/
├── tools/
│   ├── __init__.py
│   ├── base_tool.py      # Abstract base class for all tools
│   ├── web_search_tool.py # Web search implementation
│   ├── content_tool.py    # Content retrieval implementation
│   └── tool_registry.py   # Tool registration and management
└── tool_calling.py        # Main tool calling cog
```

#### 1.2 Base Tool Interface
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseTool(ABC):
    """Abstract base class for all tools"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON schema for tool parameters"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters"""
        pass
```

### 2. Implementation Steps

#### Phase 1: Foundation (Week 1)
1. **Create Tool Infrastructure**
   - Implement `base_tool.py` with abstract base class
   - Create `tool_registry.py` for tool management
   - Add tool configuration to `models_config.json`

2. **Update API Utils**
   - Modify `api_utils.py` to support tool calling format
   - Add methods for formatting tool responses
   - Implement tool execution loop

#### Phase 2: Tool Implementation (Week 2)
1. **Web Search Tool**
   - Migrate existing DuckDuckGo functionality to tool format
   - Add Exa API support as alternative search provider
   - Implement result ranking and relevance scoring

2. **Content Retrieval Tool**
   - Create web scraping functionality using aiohttp
   - Add content extraction and cleaning
   - Implement caching mechanism

#### Phase 3: Integration (Week 3)
1. **Tool Calling Cog**
   - Create `tool_calling.py` cog
   - Implement recursive tool calling loop
   - Add conversation history management
   - Integrate with existing chat flow

2. **Flag System**
   - Add `tool_calling` flag (default: True)
   - Modify `web_search` flag to force search tool usage
   - Update slash command parameters

#### Phase 4: Testing & Refinement (Week 4)
1. **Testing**
   - Unit tests for each tool
   - Integration tests for tool calling loop
   - Discord bot testing with various scenarios

2. **Optimization**
   - Add rate limiting for API calls
   - Implement better error handling
   - Optimize token usage

### 3. Detailed Implementation

#### 3.1 Tool Registry Implementation
```python
# cogs/tools/tool_registry.py
from typing import Dict, Type, Optional
from .base_tool import BaseTool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """Register a tool"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(name)
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-format tool schemas"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in self._tools.values()
        ]
```

#### 3.2 Modified Chat Flow
```python
# generic_chat.py modifications
async def perform_chat_query_with_tools(
    prompt: str,
    api_cog,
    tool_registry: ToolRegistry,
    channel: discord.TextChannel,
    user_id: str,
    model: str,
    use_tools: bool = True,
    force_web_search: bool = False,
    max_iterations: int = 10
) -> (str, float, str):
    """Enhanced chat query with tool calling support"""
    
    conversation_history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    if not use_tools:
        # Direct API call without tools
        return await perform_standard_chat_query(...)
    
    # Tool calling loop
    for iteration in range(max_iterations):
        # Include available tools in API call
        tools = tool_registry.get_all_schemas()
        
        response = await api_cog.send_request_with_tools(
            model=model,
            messages=conversation_history,
            tools=tools,
            tool_choice="required" if force_web_search and iteration == 0 else "auto"
        )
        
        # Process tool calls if any
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool = tool_registry.get(tool_call.function.name)
                if tool:
                    result = await tool.execute(**tool_call.function.arguments)
                    conversation_history.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call]
                    })
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
        else:
            # No more tool calls, return final response
            return response.content, elapsed, footer
    
    # Max iterations reached
    return "Maximum tool iterations reached", elapsed, footer
```

#### 3.3 Web Search Tool Implementation
```python
# cogs/tools/web_search_tool.py
from .base_tool import BaseTool
from duckduckgo_search import DDGS
import asyncio

class WebSearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_web"
    
    @property
    def description(self) -> str:
        return "Search the web for information"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Execute web search"""
        def _search():
            ddgs = DDGS()
            return list(ddgs.text(query, max_results=max_results))
        
        results = await asyncio.to_thread(_search)
        
        return {
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                }
                for r in results
            ]
        }
```

### 4. Configuration Updates

#### 4.1 Model Configuration
```json
// models_config.json additions
{
  "gpt-4o-mini": {
    "supports_tools": true,
    "tool_settings": {
      "max_iterations": 10,
      "default_enabled": true
    }
  }
}
```

#### 4.2 Command Updates
```python
# ai_commands.py modifications
@app_commands.describe(
    tool_calling="Enable tool calling (web search, content retrieval)",
    force_tools="Force at least one tool call"
)
async def chat_slash(
    self,
    interaction: Interaction,
    model: str,
    prompt: str,
    tool_calling: bool = True,  # New parameter
    force_tools: bool = False,  # Replaces web_search
    # ... other parameters
):
    # Implementation
```

### 5. Migration Path

1. **Backward Compatibility**
   - Keep existing `web_search` parameter working
   - Map `web_search=True` to `force_tools=True` with search tool
   - Gradually deprecate old parameter

2. **Feature Flags**
   - Add environment variable `ENABLE_TOOL_CALLING=false` initially
   - Test with select users before full rollout
   - Monitor performance and costs

3. **Monitoring**
   - Track tool usage statistics
   - Monitor token consumption
   - Log tool execution times
   - Track error rates

### 6. Security Considerations

1. **URL Filtering**
   - Implement domain allowlist/blocklist
   - Validate URLs before fetching
   - Add rate limiting per user

2. **Content Safety**
   - Sanitize fetched content
   - Limit content size
   - Add timeout for requests

3. **Cost Management**
   - Track API calls per tool
   - Implement cost estimation
   - Add per-user tool usage limits

### 7. Future Enhancements

1. **Additional Tools**
   - Calculator tool
   - Code execution tool (sandboxed)
   - Image analysis tool
   - Database query tool

2. **Advanced Features**
   - Tool result caching
   - Parallel tool execution
   - Custom tool creation by users
   - Tool usage analytics dashboard

### 8. Testing Plan

1. **Unit Tests**
   - Test each tool individually
   - Mock external API calls
   - Test error handling

2. **Integration Tests**
   - Test tool calling loop
   - Test with various models
   - Test rate limiting

3. **Discord Bot Tests**
   - Test slash commands
   - Test context menus
   - Test with attachments
   - Test quota integration

### 9. Documentation Updates

1. **User Documentation**
   - Update README with tool calling features
   - Add examples of tool usage
   - Document new parameters

2. **Developer Documentation**
   - Tool development guide
   - API documentation
   - Architecture diagrams

### 10. Success Metrics

1. **Performance**
   - Response time with tools < 10s average
   - Tool execution success rate > 95%
   - Token usage optimization

2. **User Experience**
   - Improved answer quality
   - Reduced hallucinations
   - Better factual accuracy

3. **System Health**
   - API error rate < 1%
   - Cost per request within budget
   - No significant increase in Discord API errors

## Conclusion

This implementation plan provides a structured approach to integrating tool calling capabilities into the Discord LLM bot. The phased approach ensures backward compatibility while gradually introducing new features. The architecture is designed to be extensible, allowing for easy addition of new tools in the future.