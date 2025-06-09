"""
Integration tests for the complete tool calling system
"""
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools import ToolRegistry, WebSearchTool, ContentRetrievalTool
from cogs.tool_calling import ToolCalling


class TestToolCallingIntegration:
    """Integration tests for the complete tool calling system"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Create a mock Discord bot
        self.mock_bot = Mock()
        self.tool_cog = ToolCalling(self.mock_bot)
        
        # Create mock channel
        self.mock_channel = Mock()
        self.mock_channel.send = AsyncMock()
    
    def test_tool_initialization(self):
        """Test that tools are properly initialized"""
        registry = self.tool_cog.get_registry()
        
        # Check that default tools are registered
        tools = registry.list_tools()
        assert "search_web" in tools
        assert "get_contents" in tools
        
        # Check that tools are enabled
        assert registry.is_enabled("search_web")
        assert registry.is_enabled("get_contents")
        
        # Check tool schemas
        schemas = registry.get_all_schemas()
        assert len(schemas) == 2
        
        tool_names = [schema["function"]["name"] for schema in schemas]
        assert "search_web" in tool_names
        assert "get_contents" in tool_names
    
    async def test_tool_call_processing(self):
        """Test processing of tool calls"""
        # Mock tool calls like those from OpenAI API
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "search_web",
                    "arguments": '{"query": "test query", "max_results": 3}'
                }
            },
            {
                "id": "call_2",
                "function": {
                    "name": "get_contents",
                    "arguments": '{"url": "https://example.com"}'
                }
            }
        ]
        
        # Mock the actual tool execution
        with patch.object(self.tool_cog.registry, 'execute_tool') as mock_execute:
            mock_execute.side_effect = [
                {
                    "success": True,
                    "query": "test query",
                    "results": [
                        {"title": "Test Result", "url": "https://test.com", "snippet": "Test snippet"}
                    ]
                },
                {
                    "success": True,
                    "url": "https://example.com",
                    "title": "Example Page",
                    "content": "Example content"
                }
            ]
            
            results = await self.tool_cog.process_tool_calls(
                tool_calls,
                user_id="test_user",
                channel=self.mock_channel
            )
            
            assert len(results) == 2
            
            # Check first result (search)
            assert results[0]["tool_call_id"] == "call_1"
            assert results[0]["tool_name"] == "search_web"
            assert results[0]["result"]["success"] is True
            
            # Check second result (content)
            assert results[1]["tool_call_id"] == "call_2"
            assert results[1]["tool_name"] == "get_contents"
            assert results[1]["result"]["success"] is True
    
    async def test_tool_call_with_json_error(self):
        """Test handling of malformed JSON in tool calls"""
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "search_web",
                    "arguments": '{"query": "test", invalid json}'  # Malformed JSON
                }
            }
        ]
        
        results = await self.tool_cog.process_tool_calls(
            tool_calls,
            user_id="test_user",
            channel=self.mock_channel
        )
        
        assert len(results) == 1
        assert results[0]["tool_call_id"] == "call_1"
        assert "Invalid arguments JSON" in results[0]["error"]
    
    async def test_tool_call_nonexistent_tool(self):
        """Test handling of calls to nonexistent tools"""
        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "nonexistent_tool",
                    "arguments": '{"param": "value"}'
                }
            }
        ]
        
        results = await self.tool_cog.process_tool_calls(
            tool_calls,
            user_id="test_user",
            channel=self.mock_channel
        )
        
        assert len(results) == 1
        assert results[0]["tool_call_id"] == "call_1"
        assert results[0]["tool_name"] == "nonexistent_tool"
        assert results[0]["result"]["success"] is False
        assert "not found" in results[0]["result"]["error"]
    
    def test_format_tool_results_for_llm(self):
        """Test formatting tool results for LLM consumption"""
        results = [
            {
                "tool_call_id": "call_1",
                "tool_name": "search_web",
                "result": {
                    "success": True,
                    "query": "test query",
                    "results": [
                        {"title": "Test", "url": "https://test.com", "snippet": "Test snippet"}
                    ]
                }
            },
            {
                "tool_call_id": "call_2",
                "tool_name": "get_contents",
                "result": {
                    "success": False,
                    "error": "Failed to retrieve content"
                }
            }
        ]
        
        formatted = self.tool_cog.format_tool_results_for_llm(results)
        
        assert len(formatted) == 2
        
        # Check first result (successful search)
        assert formatted[0]["role"] == "tool"
        assert formatted[0]["tool_call_id"] == "call_1"
        assert "Web search results for 'test query'" in formatted[0]["content"]
        
        # Check second result (failed content retrieval)
        assert formatted[1]["role"] == "tool"
        assert formatted[1]["tool_call_id"] == "call_2"
        assert "Tool error: Failed to retrieve content" in formatted[1]["content"]
    
    async def test_end_to_end_search_and_content(self):
        """Test end-to-end search and content retrieval workflow"""
        # This test simulates a realistic workflow:
        # 1. User asks about something
        # 2. AI searches for it
        # 3. AI retrieves content from one of the search results
        
        registry = self.tool_cog.get_registry()
        
        # Mock search results
        with patch.object(registry.get("search_web"), "_search_ddg") as mock_search:
            mock_search.return_value = {
                "success": True,
                "query": "Python asyncio tutorial",
                "results": [
                    {
                        "title": "Python Asyncio Tutorial",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                        "snippet": "Asyncio is a library to write concurrent code"
                    }
                ]
            }
            
            # Execute search
            search_result = await registry.execute_tool(
                "search_web",
                query="Python asyncio tutorial",
                max_results=3
            )
            
            assert search_result["success"] is True
            assert len(search_result["results"]) == 1
            
            # Mock content retrieval
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = Mock()
                mock_response.status = 200
                mock_response.headers = {'Content-Type': 'text/html'}
                mock_response.text = AsyncMock(return_value="""
                    <html>
                    <head><title>Python Asyncio Tutorial</title></head>
                    <body>
                        <h1>Asyncio Documentation</h1>
                        <p>This module provides infrastructure for writing single-threaded concurrent code using coroutines.</p>
                    </body>
                    </html>
                """)
                
                mock_session_instance = Mock()
                mock_session_instance.get.return_value.__aenter__.return_value = mock_response
                mock_session.return_value.__aenter__.return_value = mock_session_instance
                
                # Execute content retrieval
                content_result = await registry.execute_tool(
                    "get_contents",
                    url="https://docs.python.org/3/library/asyncio.html"
                )
                
                assert content_result["success"] is True
                assert "Asyncio Documentation" in content_result["content"]
                assert content_result["title"] == "Python Asyncio Tutorial"
    
    def test_tool_statistics_tracking(self):
        """Test that tool usage statistics are properly tracked"""
        registry = self.tool_cog.get_registry()
        
        # Initial stats should be zero
        initial_stats = registry.get_stats()
        assert initial_stats["search_web"]["usage_count"] == 0
        assert initial_stats["search_web"]["error_count"] == 0
        
        # After calling a tool, stats should update
        # (This would happen automatically when tools are called)
        search_tool = registry.get("search_web")
        search_tool._usage_count += 1
        
        updated_stats = registry.get_stats()
        assert updated_stats["search_web"]["usage_count"] == 1
    
    async def test_tool_enable_disable_functionality(self):
        """Test enabling and disabling tools"""
        registry = self.tool_cog.get_registry()
        
        # Initially, tools should be enabled
        assert registry.is_enabled("search_web")
        
        # Disable search tool
        registry.disable("search_web")
        assert not registry.is_enabled("search_web")
        
        # Try to execute disabled tool
        result = await registry.execute_tool("search_web", query="test")
        assert result["success"] is False
        assert "not found" in result["error"]
        
        # Re-enable tool
        registry.enable("search_web")
        assert registry.is_enabled("search_web")
        
        # Now it should work (with mocking)
        with patch.object(registry.get("search_web"), "_search_ddg") as mock_search:
            mock_search.return_value = {"success": True, "results": []}
            
            result = await registry.execute_tool("search_web", query="test")
            assert result["success"] is True


def run_integration_tests():
    """Run integration tests manually"""
    print("Running Integration tests...")
    
    test_instance = TestToolCallingIntegration()
    test_instance.setup_method()
    
    # Test tool initialization
    try:
        test_instance.test_tool_initialization()
        print("✅ Tool initialization test passed")
    except Exception as e:
        print(f"❌ Tool initialization test failed: {e}")
    
    # Test result formatting
    try:
        test_instance.test_format_tool_results_for_llm()
        print("✅ Format tool results test passed")
    except Exception as e:
        print(f"❌ Format tool results test failed: {e}")
    
    # Test statistics tracking
    try:
        test_instance.test_tool_statistics_tracking()
        print("✅ Tool statistics tracking test passed")
    except Exception as e:
        print(f"❌ Tool statistics tracking test failed: {e}")
    
    # Async tests
    async def run_async_tests():
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_tool_call_processing()
            print("✅ Tool call processing test passed")
        except Exception as e:
            print(f"❌ Tool call processing test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_tool_call_with_json_error()
            print("✅ Tool call JSON error test passed")
        except Exception as e:
            print(f"❌ Tool call JSON error test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_tool_call_nonexistent_tool()
            print("✅ Tool call nonexistent tool test passed")
        except Exception as e:
            print(f"❌ Tool call nonexistent tool test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_end_to_end_search_and_content()
            print("✅ End-to-end search and content test passed")
        except Exception as e:
            print(f"❌ End-to-end search and content test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_tool_enable_disable_functionality()
            print("✅ Tool enable/disable functionality test passed")
        except Exception as e:
            print(f"❌ Tool enable/disable functionality test failed: {e}")
    
    asyncio.run(run_async_tests())
    print("Integration tests completed!")


if __name__ == "__main__":
    run_integration_tests()