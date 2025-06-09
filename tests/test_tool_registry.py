"""
Test cases for ToolRegistry class
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools.tool_registry import ToolRegistry
from cogs.tools.base_tool import BaseTool


class MockTool(BaseTool):
    """Mock tool for testing"""
    
    def __init__(self, name: str):
        super().__init__()
        self._name = name
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return f"Mock tool {self._name}"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Input parameter"
                }
            },
            "required": ["input"]
        }
    
    async def execute(self, **kwargs) -> dict:
        if kwargs.get("input") == "error":
            raise ValueError("Mock error")
        
        return {
            "success": True,
            "tool": self._name,
            "input": kwargs.get("input")
        }


class TestToolRegistry:
    """Test cases for ToolRegistry"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.registry = ToolRegistry()
        self.tool1 = MockTool("tool1")
        self.tool2 = MockTool("tool2")
    
    def test_register_tool(self):
        """Test tool registration"""
        self.registry.register(self.tool1, enabled=True)
        
        assert "tool1" in self.registry.list_tools(enabled_only=False)
        assert "tool1" in self.registry.list_tools(enabled_only=True)
        assert self.registry.is_enabled("tool1")
    
    def test_register_tool_disabled(self):
        """Test registering disabled tool"""
        self.registry.register(self.tool1, enabled=False)
        
        assert "tool1" in self.registry.list_tools(enabled_only=False)
        assert "tool1" not in self.registry.list_tools(enabled_only=True)
        assert not self.registry.is_enabled("tool1")
    
    def test_register_invalid_tool(self):
        """Test registering invalid tool"""
        try:
            self.registry.register("not_a_tool")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected
    
    def test_get_tool(self):
        """Test getting tools"""
        self.registry.register(self.tool1, enabled=True)
        self.registry.register(self.tool2, enabled=False)
        
        # Test get
        assert self.registry.get("tool1") == self.tool1
        assert self.registry.get("tool2") == self.tool2
        assert self.registry.get("nonexistent") is None
        
        # Test get_enabled
        assert self.registry.get_enabled("tool1") == self.tool1
        assert self.registry.get_enabled("tool2") is None
        assert self.registry.get_enabled("nonexistent") is None
    
    def test_enable_disable_tools(self):
        """Test enabling and disabling tools"""
        self.registry.register(self.tool1, enabled=False)
        
        # Enable tool
        assert self.registry.enable("tool1")
        assert self.registry.is_enabled("tool1")
        
        # Disable tool
        assert self.registry.disable("tool1")
        assert not self.registry.is_enabled("tool1")
        
        # Test with nonexistent tool
        assert not self.registry.enable("nonexistent")
        assert not self.registry.disable("nonexistent")
    
    def test_unregister_tool(self):
        """Test tool unregistration"""
        self.registry.register(self.tool1, enabled=True)
        
        assert "tool1" in self.registry.list_tools()
        
        self.registry.unregister("tool1")
        
        assert "tool1" not in self.registry.list_tools()
        assert self.registry.get("tool1") is None
    
    def test_get_schemas(self):
        """Test getting OpenAI schemas"""
        self.registry.register(self.tool1, enabled=True)
        self.registry.register(self.tool2, enabled=False)
        
        # Test enabled only
        schemas = self.registry.get_all_schemas(enabled_only=True)
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "tool1"
        
        # Test all tools
        schemas = self.registry.get_all_schemas(enabled_only=False)
        assert len(schemas) == 2
        names = [s["function"]["name"] for s in schemas]
        assert "tool1" in names
        assert "tool2" in names
    
    def test_get_stats(self):
        """Test getting tool statistics"""
        self.registry.register(self.tool1, enabled=True)
        self.registry.register(self.tool2, enabled=False)
        
        stats = self.registry.get_stats()
        
        assert "tool1" in stats
        assert "tool2" in stats
        assert stats["tool1"]["enabled"] is True
        assert stats["tool2"]["enabled"] is False
        assert stats["tool1"]["usage_count"] == 0
        assert stats["tool1"]["error_count"] == 0
    
    async def test_execute_tool_success(self):
        """Test successful tool execution"""
        self.registry.register(self.tool1, enabled=True)
        
        result = await self.registry.execute_tool("tool1", input="test")
        
        assert result["success"] is True
        assert result["tool"] == "tool1"
        assert result["input"] == "test"
    
    async def test_execute_tool_not_found(self):
        """Test executing nonexistent tool"""
        result = await self.registry.execute_tool("nonexistent", input="test")
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    async def test_execute_tool_disabled(self):
        """Test executing disabled tool"""
        self.registry.register(self.tool1, enabled=False)
        
        result = await self.registry.execute_tool("tool1", input="test")
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    async def test_execute_tool_validation_error(self):
        """Test executing tool with validation error"""
        self.registry.register(self.tool1, enabled=True)
        
        result = await self.registry.execute_tool("tool1")  # Missing required parameter
        
        assert result["success"] is False
        assert "Missing required parameter" in result["error"]
    
    async def test_execute_tool_execution_error(self):
        """Test executing tool with execution error"""
        self.registry.register(self.tool1, enabled=True)
        
        result = await self.registry.execute_tool("tool1", input="error")
        
        assert result["success"] is False
        assert "Mock error" in result["error"]


def run_registry_tests():
    """Run tool registry tests manually"""
    print("Running ToolRegistry tests...")
    
    test_instance = TestToolRegistry()
    test_instance.setup_method()
    
    # Test registration
    try:
        test_instance.test_register_tool()
        print("✅ Register tool test passed")
    except Exception as e:
        print(f"❌ Register tool test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_register_tool_disabled()
        print("✅ Register disabled tool test passed")
    except Exception as e:
        print(f"❌ Register disabled tool test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_register_invalid_tool()
        print("✅ Register invalid tool test passed")
    except Exception as e:
        print(f"❌ Register invalid tool test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_get_tool()
        print("✅ Get tool test passed")
    except Exception as e:
        print(f"❌ Get tool test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_enable_disable_tools()
        print("✅ Enable/disable tools test passed")
    except Exception as e:
        print(f"❌ Enable/disable tools test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_unregister_tool()
        print("✅ Unregister tool test passed")
    except Exception as e:
        print(f"❌ Unregister tool test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_get_schemas()
        print("✅ Get schemas test passed")
    except Exception as e:
        print(f"❌ Get schemas test failed: {e}")
    
    # Reset
    test_instance.setup_method()
    
    try:
        test_instance.test_get_stats()
        print("✅ Get stats test passed")
    except Exception as e:
        print(f"❌ Get stats test failed: {e}")
    
    # Async tests
    async def run_async_tests():
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_execute_tool_success()
            print("✅ Execute tool success test passed")
        except Exception as e:
            print(f"❌ Execute tool success test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_execute_tool_not_found()
            print("✅ Execute tool not found test passed")
        except Exception as e:
            print(f"❌ Execute tool not found test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_execute_tool_disabled()
            print("✅ Execute disabled tool test passed")
        except Exception as e:
            print(f"❌ Execute disabled tool test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_execute_tool_validation_error()
            print("✅ Execute tool validation error test passed")
        except Exception as e:
            print(f"❌ Execute tool validation error test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_execute_tool_execution_error()
            print("✅ Execute tool execution error test passed")
        except Exception as e:
            print(f"❌ Execute tool execution error test failed: {e}")
    
    asyncio.run(run_async_tests())
    print("ToolRegistry tests completed!")


if __name__ == "__main__":
    run_registry_tests()