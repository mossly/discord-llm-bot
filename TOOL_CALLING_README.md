# Tool Calling Feature

## Overview
The Discord LLM bot now supports tool calling, allowing AI models to dynamically use tools like web search and content retrieval to provide more accurate and up-to-date responses.

## Features

### Available Tools
1. **Web Search Tool** (`search_web`)
   - Searches the web using DuckDuckGo (or Exa if configured)
   - Returns relevant search results with titles, URLs, and snippets
   - Configurable result count (1-10 results)

2. **Content Retrieval Tool** (`get_contents`)
   - Fetches and extracts content from web pages
   - Returns cleaned markdown content with title
   - Optional link extraction
   - Content length limiting for performance

### Usage

#### Slash Commands
The `/chat` command now includes tool calling parameters:

```
/chat model:gpt-4o-mini prompt:"What's happening with AI today?" tool_calling:True
```

**Parameters:**
- `tool_calling` (default: True) - Enable AI to use tools
- `web_search` (default: False) - Force web search on first iteration
- `fun` (default: False) - Fun mode with emojis
- `max_tokens` (default: 8000) - Maximum response tokens

#### Context Menu
Right-click any message and select "AI Reply" to get context-aware responses with tool support.

**New UI Controls:**
- **Tools: ON/OFF** - Toggle tool calling
- **Force Search: ON/OFF** - Force web search (requires tools enabled)
- **Fun Mode: ON/OFF** - Toggle fun mode

### Model Support
Tool calling is supported by the following models:
- GPT-4o-mini ✅
- o4-mini ✅
- Claude 3.7 Sonnet ✅
- DeepSeek R1 ✅
- Gemini 2.5 Pro Preview ✅
- Gemini 2.5 Flash Preview ✅
- Grok 3 Beta ✅

### Backward Compatibility
- The `web_search` parameter still works and forces a web search tool call
- Models without tool support automatically fall back to standard chat
- All existing functionality remains unchanged

### How It Works

1. **Tool Detection**: AI models analyze user queries and determine if tools are needed
2. **Tool Execution**: The bot executes requested tools (web search, content retrieval)
3. **Iterative Process**: AI can call multiple tools in sequence (up to 10 iterations)
4. **Final Response**: AI synthesizes tool results into a comprehensive answer

### Examples

#### Web Search Example
```
User: "What's the latest news about OpenAI?"
AI: [Calls search_web tool]
Bot: Searches for "OpenAI latest news"
AI: [Processes results and provides summary]
```

#### Content Retrieval Example
```
User: "Summarize this article: https://example.com/article"
AI: [Calls get_contents tool]
Bot: Fetches and extracts article content
AI: [Provides summary of the content]
```

### Configuration

#### Environment Variables
- `EXA_API_KEY` (optional) - For Exa search provider instead of DuckDuckGo
- `DUCK_PROXY` (optional) - Proxy for DuckDuckGo searches

#### Admin Commands
```
!tools           # List available tools and usage stats
!toggle_tool web_search  # Enable/disable specific tools
```

### Performance
- Tool calls are included in quota calculations
- Multiple iterations may increase token usage
- Content retrieval is limited to 50KB per page
- Web searches are limited to 10 results maximum

### Error Handling
- Tools gracefully degrade on failures
- Falls back to standard chat if tools fail
- Respects user quotas and rate limits
- Validates tool parameters before execution

### Future Enhancements
- Calculator tool for mathematical operations
- Code execution tool (sandboxed)
- Database query tool
- Custom tool creation by administrators
- Tool result caching for performance
- Parallel tool execution

## Installation Notes

### New Dependencies
```bash
pip install beautifulsoup4 html2text
```

### File Structure
```
cogs/
├── tools/
│   ├── __init__.py
│   ├── base_tool.py      # Base tool interface
│   ├── web_search_tool.py # Web search implementation
│   ├── content_tool.py    # Content retrieval
│   └── tool_registry.py   # Tool management
└── tool_calling.py        # Main tool calling cog
```

## Testing
Run the test script to verify tool functionality:
```bash
python3 test_tools.py
```

This will test both web search and content retrieval tools independently.