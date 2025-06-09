"""
Test cases for WebSearchTool
"""
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools.web_search_tool import WebSearchTool


class TestWebSearchTool:
    """Test cases for WebSearchTool"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.tool = WebSearchTool(use_ddg=True)
    
    def test_tool_properties(self):
        """Test tool properties"""
        assert self.tool.name == "search_web"
        assert "search" in self.tool.description.lower()
        assert "query" in self.tool.parameters["properties"]
        assert "max_results" in self.tool.parameters["properties"]
        assert "query" in self.tool.parameters["required"]
    
    def test_parameter_validation(self):
        """Test parameter validation"""
        # Valid parameters
        error = self.tool.validate_parameters(query="test query", max_results=5)
        assert error is None
        
        # Missing required parameter
        error = self.tool.validate_parameters(max_results=5)
        assert "Missing required parameter: query" in error
        
        # Wrong type
        error = self.tool.validate_parameters(query="test", max_results="not_int")
        assert "must be an integer" in error
    
    @patch('cogs.tools.web_search_tool.asyncio.to_thread')
    async def test_ddg_search_success(self, mock_to_thread):
        """Test successful DuckDuckGo search"""
        # Mock the search results
        mock_results = [
            {
                "title": "Test Result 1",
                "href": "https://example.com/1",
                "body": "Test snippet 1"
            },
            {
                "title": "Test Result 2",
                "href": "https://example.com/2",
                "body": "Test snippet 2"
            }
        ]
        
        mock_to_thread.return_value = mock_results
        
        result = await self.tool.execute(query="test query", max_results=2)
        
        assert result["success"] is True
        assert result["query"] == "test query"
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Test Result 1"
        assert result["results"][0]["url"] == "https://example.com/1"
        assert result["results"][0]["snippet"] == "Test snippet 1"
    
    @patch('cogs.tools.web_search_tool.asyncio.to_thread')
    async def test_ddg_search_failure(self, mock_to_thread):
        """Test DuckDuckGo search failure"""
        mock_to_thread.return_value = None
        
        result = await self.tool.execute(query="test query")
        
        assert result["success"] is False
        assert "Search failed" in result["error"]
    
    async def test_max_results_limit(self):
        """Test max results limit enforcement"""
        # Mock the internal DDG search method
        with patch.object(self.tool, '_search_ddg') as mock_search:
            mock_search.return_value = {"success": True, "results": []}
            
            # Test normal limit
            await self.tool.execute(query="test", max_results=5)
            mock_search.assert_called_with("test", 5)
            
            # Test over limit
            await self.tool.execute(query="test", max_results=15)
            mock_search.assert_called_with("test", 10)  # Should be capped at 10
    
    def test_format_results_for_llm(self):
        """Test formatting results for LLM consumption"""
        # Test successful results
        results = {
            "success": True,
            "query": "test query",
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "snippet": "Test snippet"
                }
            ]
        }
        
        formatted = self.tool.format_results_for_llm(results)
        
        assert "Web search results for 'test query'" in formatted
        assert "Test Result" in formatted
        assert "https://example.com" in formatted
        assert "Test snippet" in formatted
        
        # Test failed results
        failed_results = {
            "success": False,
            "error": "Search failed"
        }
        
        formatted = self.tool.format_results_for_llm(failed_results)
        assert "Search failed" in formatted
        
        # Test empty results
        empty_results = {
            "success": True,
            "results": []
        }
        
        formatted = self.tool.format_results_for_llm(empty_results)
        assert "No search results found" in formatted
    
    @patch('aiohttp.ClientSession')
    async def test_exa_search_success(self, mock_session):
        """Test successful Exa API search"""
        # Create a tool with Exa enabled
        tool = WebSearchTool(use_ddg=False, exa_api_key="test_key")
        
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [
                {
                    "title": "Exa Result",
                    "url": "https://example.com",
                    "snippet": "Exa snippet"
                }
            ]
        })
        
        mock_session_instance = Mock()
        mock_session_instance.post.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await tool.execute(query="test query")
        
        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Exa Result"
    
    @patch('aiohttp.ClientSession')
    async def test_exa_search_api_error(self, mock_session):
        """Test Exa API error handling"""
        tool = WebSearchTool(use_ddg=False, exa_api_key="test_key")
        
        # Mock HTTP error response
        mock_response = Mock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad request")
        
        mock_session_instance = Mock()
        mock_session_instance.post.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await tool.execute(query="test query")
        
        assert result["success"] is False
        assert "Exa API error" in result["error"]
    
    async def test_no_provider_configured(self):
        """Test behavior when no search provider is configured"""
        tool = WebSearchTool(use_ddg=False, exa_api_key=None)
        
        result = await tool.execute(query="test query")
        
        assert result["success"] is False
        assert "No search provider configured" in result["error"]


def run_web_search_tests():
    """Run web search tool tests manually"""
    print("Running WebSearchTool tests...")
    
    test_instance = TestWebSearchTool()
    test_instance.setup_method()
    
    # Test properties
    try:
        test_instance.test_tool_properties()
        print("✅ Tool properties test passed")
    except Exception as e:
        print(f"❌ Tool properties test failed: {e}")
    
    # Test parameter validation
    try:
        test_instance.test_parameter_validation()
        print("✅ Parameter validation test passed")
    except Exception as e:
        print(f"❌ Parameter validation test failed: {e}")
    
    # Test result formatting
    try:
        test_instance.test_format_results_for_llm()
        print("✅ Format results test passed")
    except Exception as e:
        print(f"❌ Format results test failed: {e}")
    
    # Async tests
    async def run_async_tests():
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_ddg_search_success()
            print("✅ DuckDuckGo search success test passed")
        except Exception as e:
            print(f"❌ DuckDuckGo search success test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_ddg_search_failure()
            print("✅ DuckDuckGo search failure test passed")
        except Exception as e:
            print(f"❌ DuckDuckGo search failure test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_max_results_limit()
            print("✅ Max results limit test passed")
        except Exception as e:
            print(f"❌ Max results limit test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_exa_search_success()
            print("✅ Exa search success test passed")
        except Exception as e:
            print(f"❌ Exa search success test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_exa_search_api_error()
            print("✅ Exa search API error test passed")
        except Exception as e:
            print(f"❌ Exa search API error test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_no_provider_configured()
            print("✅ No provider configured test passed")
        except Exception as e:
            print(f"❌ No provider configured test failed: {e}")
    
    asyncio.run(run_async_tests())
    print("WebSearchTool tests completed!")


if __name__ == "__main__":
    run_web_search_tests()