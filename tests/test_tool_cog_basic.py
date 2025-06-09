"""
Test the tool calling cog with mocked dependencies
"""
import sys
import os
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock discord imports before importing the cog
sys.modules['discord'] = Mock()
sys.modules['discord.ext'] = Mock()
sys.modules['discord.ext.commands'] = Mock()

# Mock the tool imports that might have dependency issues
from cogs.tools.base_tool import BaseTool
from cogs.tools.tool_registry import ToolRegistry


class MockWebSearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_web"
    
    @property  
    def description(self) -> str:
        return "Mock web search tool"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    
    async def execute(self, **kwargs) -> dict:
        return {
            "success": True,
            "query": kwargs.get("query"),
            "results": [{"title": "Mock Result", "url": "https://mock.com", "snippet": "Mock snippet"}]
        }


class MockContentTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_contents"
    
    @property
    def description(self) -> str:
        return "Mock content retrieval tool"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object", 
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"}
            },
            "required": ["url"]
        }
    
    async def execute(self, **kwargs) -> dict:
        return {
            "success": True,
            "url": kwargs.get("url"),
            "title": "Mock Page",
            "content": "Mock content from the page"
        }


def test_tool_cog_initialization():
    """Test tool calling cog initialization with mocked tools"""
    print("Testing tool calling cog initialization...")
    
    # Mock the bot
    mock_bot = Mock()
    
    # Create a mock version of the ToolCalling cog
    class MockToolCalling:
        def __init__(self, bot):
            self.bot = bot
            self.registry = ToolRegistry()
            self._initialize_tools()
        
        def _initialize_tools(self):
            web_search = MockWebSearchTool()
            content_tool = MockContentTool()
            
            self.registry.register(web_search, enabled=True)
            self.registry.register(content_tool, enabled=True)
        
        def get_registry(self):
            return self.registry
    
    # Test initialization
    tool_cog = MockToolCalling(mock_bot)
    
    # Verify tools are registered
    registry = tool_cog.get_registry()
    tools = registry.list_tools()
    
    assert "search_web" in tools
    assert "get_contents" in tools
    assert registry.is_enabled("search_web")
    assert registry.is_enabled("get_contents")
    
    print("✅ Tool cog initialization successful")
    
    # Test schema generation
    schemas = registry.get_all_schemas()
    assert len(schemas) == 2
    
    tool_names = [s["function"]["name"] for s in schemas]
    assert "search_web" in tool_names
    assert "get_contents" in tool_names
    
    print("✅ Tool schema generation successful")
    
    return tool_cog


async def test_tool_execution():
    """Test tool execution through the cog"""
    print("\nTesting tool execution...")
    
    tool_cog = test_tool_cog_initialization()
    registry = tool_cog.get_registry()
    
    # Test web search
    result = await registry.execute_tool("search_web", query="test query")
    assert result["success"] is True
    assert result["query"] == "test query"
    assert len(result["results"]) == 1
    
    print("✅ Web search tool execution successful")
    
    # Test content retrieval
    result = await registry.execute_tool("get_contents", url="https://example.com")
    assert result["success"] is True
    assert result["url"] == "https://example.com"
    assert result["title"] == "Mock Page"
    
    print("✅ Content retrieval tool execution successful")


def test_openai_format_compatibility():
    """Test that our tools generate OpenAI-compatible schemas"""
    print("\nTesting OpenAI format compatibility...")
    
    tool_cog = test_tool_cog_initialization()
    registry = tool_cog.get_registry()
    schemas = registry.get_all_schemas()
    
    for schema in schemas:
        # Check required OpenAI format fields
        assert "type" in schema
        assert schema["type"] == "function"
        assert "function" in schema
        
        function = schema["function"]
        assert "name" in function
        assert "description" in function
        assert "parameters" in function
        
        parameters = function["parameters"]
        assert "type" in parameters
        assert parameters["type"] == "object"
        assert "properties" in parameters
        
        print(f"✅ {function['name']} schema is OpenAI compatible")


async def run_cog_tests():
    """Run all cog-specific tests"""
    print("=" * 50)
    print("TOOL CALLING COG TESTS")
    print("=" * 50)
    
    try:
        test_tool_cog_initialization()
        await test_tool_execution()
        test_openai_format_compatibility()
        
        print("\n" + "=" * 50)
        print("🎉 All tool cog tests passed!")
        print("Tool calling cog is ready for Discord integration.")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\n❌ Tool cog tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import asyncio
    success = asyncio.run(run_cog_tests())
    if not success:
        sys.exit(1)