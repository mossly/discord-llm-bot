"""
Test cases for BaseTool abstract class
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools.base_tool import BaseTool


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
                },
                "optional_param": {
                    "type": "integer",
                    "description": "An optional parameter"
                }
            },
            "required": ["test_param"]
        }
    
    async def execute(self, **kwargs) -> dict:
        if kwargs.get("test_param") == "error":
            raise ValueError("Test error")
        
        return {
            "success": True,
            "message": f"Executed with {kwargs}"
        }


class TestBaseTool:
    """Test cases for BaseTool"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.tool = MockTool()
    
    def test_tool_properties(self):
        """Test tool property methods"""
        assert self.tool.name == "mock_tool"
        assert self.tool.description == "A mock tool for testing"
        assert isinstance(self.tool.parameters, dict)
        assert self.tool.usage_count == 0
        assert self.tool.error_count == 0
    
    def test_openai_schema(self):
        """Test OpenAI schema generation"""
        schema = self.tool.get_openai_schema()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert schema["function"]["description"] == "A mock tool for testing"
        assert "parameters" in schema["function"]
    
    def test_parameter_validation_success(self):
        """Test successful parameter validation"""
        error = self.tool.validate_parameters(test_param="value", optional_param=42)
        assert error is None
    
    def test_parameter_validation_missing_required(self):
        """Test validation with missing required parameter"""
        error = self.tool.validate_parameters(optional_param=42)
        assert error == "Missing required parameter: test_param"
    
    def test_parameter_validation_wrong_type(self):
        """Test validation with wrong parameter type"""
        error = self.tool.validate_parameters(test_param="value", optional_param="not_int")
        assert "must be an integer" in error
    
    async def test_successful_execution(self):
        """Test successful tool execution"""
        result = await self.tool(test_param="test_value")
        
        assert result["success"] is True
        assert "test_value" in result["message"]
        assert self.tool.usage_count == 1
        assert self.tool.error_count == 0
    
    async def test_execution_with_error(self):
        """Test tool execution with error"""
        result = await self.tool(test_param="error")
        
        assert result["success"] is False
        assert "error" in result
        assert self.tool.usage_count == 1
        assert self.tool.error_count == 1


def run_base_tool_tests():
    """Run base tool tests manually"""
    print("Running BaseTool tests...")
    
    test_instance = TestBaseTool()
    test_instance.setup_method()
    
    # Test properties
    try:
        test_instance.test_tool_properties()
        print("✅ Tool properties test passed")
    except Exception as e:
        print(f"❌ Tool properties test failed: {e}")
    
    # Test OpenAI schema
    try:
        test_instance.test_openai_schema()
        print("✅ OpenAI schema test passed")
    except Exception as e:
        print(f"❌ OpenAI schema test failed: {e}")
    
    # Test parameter validation
    try:
        test_instance.test_parameter_validation_success()
        print("✅ Parameter validation success test passed")
    except Exception as e:
        print(f"❌ Parameter validation success test failed: {e}")
    
    try:
        test_instance.test_parameter_validation_missing_required()
        print("✅ Parameter validation missing required test passed")
    except Exception as e:
        print(f"❌ Parameter validation missing required test failed: {e}")
    
    try:
        test_instance.test_parameter_validation_wrong_type()
        print("✅ Parameter validation wrong type test passed")
    except Exception as e:
        print(f"❌ Parameter validation wrong type test failed: {e}")
    
    # Test async execution
    async def run_async_tests():
        try:
            await test_instance.test_successful_execution()
            print("✅ Successful execution test passed")
        except Exception as e:
            print(f"❌ Successful execution test failed: {e}")
        
        # Reset for next test
        test_instance.setup_method()
        
        try:
            await test_instance.test_execution_with_error()
            print("✅ Execution with error test passed")
        except Exception as e:
            print(f"❌ Execution with error test failed: {e}")
    
    asyncio.run(run_async_tests())
    print("BaseTool tests completed!")


if __name__ == "__main__":
    run_base_tool_tests()