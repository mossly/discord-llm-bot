"""
Basic functionality tests without external dependencies
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools.base_tool import BaseTool
from cogs.tools.tool_registry import ToolRegistry


class MockTool(BaseTool):
    """Mock tool for testing BaseTool functionality"""
    
    @property
    def name(self) -> str:
        return "mock_tool"
    
    @property
    def description(self) -> str:
        return "A mock tool for testing"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "test_param": {
                    "type": "string",
                    "description": "A test parameter"
                }
            },
            "required": ["test_param"]
        }
    
    async def execute(self, **kwargs) -> dict:
        return {
            "success": True,
            "message": f"Executed with {kwargs}"
        }


async def test_basic_tool_functionality():
    """Test basic tool functionality"""
    print("Testing basic tool functionality...")
    
    # Test tool creation
    tool = MockTool()
    assert tool.name == "mock_tool"
    assert tool.description == "A mock tool for testing"
    print("✅ Tool creation and properties")
    
    # Test OpenAI schema generation
    schema = tool.get_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mock_tool"
    print("✅ OpenAI schema generation")
    
    # Test parameter validation
    error = tool.validate_parameters(test_param="value")
    assert error is None
    print("✅ Parameter validation success")
    
    error = tool.validate_parameters()
    assert "Missing required parameter" in error
    print("✅ Parameter validation failure")
    
    # Test tool execution
    result = await tool(test_param="test_value")
    assert result["success"] is True
    assert tool.usage_count == 1
    print("✅ Tool execution")


async def test_tool_registry():
    """Test tool registry functionality"""
    print("\nTesting tool registry functionality...")
    
    # Create registry and tools
    registry = ToolRegistry()
    tool1 = MockTool()
    
    # Test registration
    registry.register(tool1, enabled=True)
    assert "mock_tool" in registry.list_tools()
    assert registry.is_enabled("mock_tool")
    print("✅ Tool registration")
    
    # Test getting tools
    retrieved_tool = registry.get("mock_tool")
    assert retrieved_tool == tool1
    print("✅ Tool retrieval")
    
    # Test schemas
    schemas = registry.get_all_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "mock_tool"
    print("✅ Schema generation")
    
    # Test tool execution through registry
    result = await registry.execute_tool("mock_tool", test_param="registry_test")
    assert result["success"] is True
    print("✅ Tool execution through registry")
    
    # Test enable/disable
    registry.disable("mock_tool")
    assert not registry.is_enabled("mock_tool")
    
    result = await registry.execute_tool("mock_tool", test_param="test")
    assert result["success"] is False
    print("✅ Tool enable/disable")


async def test_error_handling():
    """Test error handling"""
    print("\nTesting error handling...")
    
    class ErrorTool(BaseTool):
        @property
        def name(self) -> str:
            return "error_tool"
        
        @property
        def description(self) -> str:
            return "A tool that throws errors"
        
        @property
        def parameters(self) -> dict:
            return {
                "type": "object",
                "properties": {
                    "should_error": {"type": "boolean"}
                },
                "required": ["should_error"]
            }
        
        async def execute(self, **kwargs) -> dict:
            if kwargs.get("should_error"):
                raise ValueError("Test error")
            return {"success": True}
    
    # Test error handling in tool
    error_tool = ErrorTool()
    result = await error_tool(should_error=True)
    assert result["success"] is False
    assert "Test error" in result["error"]
    assert error_tool.error_count == 1
    print("✅ Tool error handling")
    
    # Test normal execution
    result = await error_tool(should_error=False)
    assert result["success"] is True
    print("✅ Tool normal execution after error")


def test_type_annotations():
    """Test that type annotations work correctly"""
    print("\nTesting type annotations...")
    
    # Test that we can import generic_chat functions
    try:
        from utils.response_formatter import build_standardized_footer
        footer = build_standardized_footer("test_model", 100, 50, 0.01, 2.5)
        assert "test_model" in footer
        assert "100 input tokens" in footer
        print("✅ Generic chat import and function")
    except Exception as e:
        print(f"❌ Generic chat import failed: {e}")

    # Test tuple type annotations
    from typing import get_type_hints
    try:
        # This should not raise an error with Python 3.9+
        from utils.generic_chat import perform_chat_query
        hints = get_type_hints(perform_chat_query)
        print("✅ Type annotations work correctly")
    except Exception as e:
        print(f"❌ Type annotations failed: {e}")


async def run_basic_tests():
    """Run all basic tests"""
    print("=" * 50)
    print("BASIC FUNCTIONALITY TESTS")
    print("=" * 50)
    
    try:
        await test_basic_tool_functionality()
        await test_tool_registry()
        await test_error_handling()
        test_type_annotations()
        
        print("\n" + "=" * 50)
        print("🎉 All basic tests passed!")
        print("Tool calling system core functionality is working correctly.")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\n❌ Basic tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_basic_tests())
    if not success:
        sys.exit(1)