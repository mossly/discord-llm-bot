"""
Test cases for ContentRetrievalTool
"""
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.tools.content_tool import ContentRetrievalTool


class TestContentRetrievalTool:
    """Test cases for ContentRetrievalTool"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.tool = ContentRetrievalTool(timeout=5, max_content_length=1000)
    
    def test_tool_properties(self):
        """Test tool properties"""
        assert self.tool.name == "get_contents"
        assert "retrieve" in self.tool.description.lower()
        assert "url" in self.tool.parameters["properties"]
        assert "extract_links" in self.tool.parameters["properties"]
        assert "url" in self.tool.parameters["required"]
    
    def test_parameter_validation(self):
        """Test parameter validation"""
        # Valid parameters
        error = self.tool.validate_parameters(url="https://example.com", extract_links=True)
        assert error is None
        
        # Missing required parameter
        error = self.tool.validate_parameters(extract_links=True)
        assert "Missing required parameter: url" in error
        
        # Wrong type
        error = self.tool.validate_parameters(url="https://example.com", extract_links="not_bool")
        assert "must be a boolean" in error
    
    async def test_invalid_url(self):
        """Test handling of invalid URLs"""
        # Test malformed URL
        result = await self.tool.execute(url="not-a-url")
        assert result["success"] is False
        assert "Invalid URL" in result["error"]
        
        # Test URL without scheme
        result = await self.tool.execute(url="example.com")
        assert result["success"] is False
        assert "Invalid URL" in result["error"]
    
    @patch('aiohttp.ClientSession')
    async def test_successful_html_content_retrieval(self, mock_session):
        """Test successful HTML content retrieval"""
        mock_html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Main Heading</h1>
            <p>Test paragraph content.</p>
            <a href="https://link1.com">Link 1</a>
            <a href="https://link2.com">Link 2</a>
        </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com", extract_links=True)
        
        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["title"] == "Test Page"
        assert "Main Heading" in result["content"]
        assert "Test paragraph content" in result["content"]
        assert "links" in result
        assert len(result["links"]) == 2
    
    @patch('aiohttp.ClientSession')
    async def test_plain_text_content_retrieval(self, mock_session):
        """Test plain text content retrieval"""
        mock_text = "This is plain text content.\nSecond line of content."
        
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/plain'}
        mock_response.text = AsyncMock(return_value=mock_text)
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com/file.txt")
        
        assert result["success"] is True
        assert result["content"] == mock_text
        assert result["title"] == "This is plain text content."  # First line as title
    
    @patch('aiohttp.ClientSession')
    async def test_http_error_handling(self, mock_session):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.status = 404
        mock_response.reason = "Not Found"
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com/notfound")
        
        assert result["success"] is False
        assert "HTTP 404" in result["error"]
    
    @patch('aiohttp.ClientSession')
    async def test_unsupported_content_type(self, mock_session):
        """Test unsupported content type handling"""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'application/pdf'}
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com/file.pdf")
        
        assert result["success"] is False
        assert "Unsupported content type" in result["error"]
    
    @patch('aiohttp.ClientSession')
    async def test_timeout_handling(self, mock_session):
        """Test timeout handling"""
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = asyncio.TimeoutError()
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com")
        
        assert result["success"] is False
        assert "Timeout" in result["error"]
    
    @patch('aiohttp.ClientSession')
    async def test_content_length_truncation(self, mock_session):
        """Test content length truncation"""
        # Create content longer than max_content_length
        long_content = "x" * 2000  # Tool is configured with max_content_length=1000
        mock_html = f"<html><body><p>{long_content}</p></body></html>"
        
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        result = await self.tool.execute(url="https://example.com")
        
        assert result["success"] is True
        assert len(result["content"]) <= 1000
        assert result["truncated"] is True
    
    def test_format_content_for_llm(self):
        """Test formatting content for LLM consumption"""
        # Test successful result
        result = {
            "success": True,
            "url": "https://example.com",
            "title": "Test Page",
            "content": "Test content here",
            "content_length": 17,
            "truncated": False,
            "links": [
                {"text": "Link 1", "url": "https://link1.com"},
                {"text": "Link 2", "url": "https://link2.com"}
            ]
        }
        
        formatted = self.tool.format_content_for_llm(result)
        
        assert "Content from https://example.com" in formatted
        assert "Title: Test Page" in formatted
        assert "Test content here" in formatted
        assert "Extracted links:" in formatted
        assert "Link 1: https://link1.com" in formatted
        
        # Test failed result
        failed_result = {
            "success": False,
            "error": "Content retrieval failed"
        }
        
        formatted = self.tool.format_content_for_llm(failed_result)
        assert "Content retrieval failed" in formatted
        
        # Test truncated result
        truncated_result = {
            "success": True,
            "url": "https://example.com",
            "title": "Test Page",
            "content": "Test content",
            "content_length": 5000,
            "truncated": True
        }
        
        formatted = self.tool.format_content_for_llm(truncated_result)
        assert "Content truncated at 5000 characters" in formatted
    
    @patch('asyncio.to_thread')
    async def test_html_content_extraction(self, mock_to_thread):
        """Test HTML content extraction with BeautifulSoup"""
        mock_html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <script>console.log('remove this');</script>
            <style>body { color: red; }</style>
            <main>
                <h1>Main Content</h1>
                <p>Important paragraph.</p>
                <a href="/link1">Internal Link</a>
            </main>
        </body>
        </html>
        """
        
        # Mock the thread execution to return processed content
        def mock_process():
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(mock_html, 'html.parser')
            
            # Remove script and style
            for script in soup(["script", "style"]):
                script.decompose()
            
            main_content = soup.find('main') or soup.find('body') or soup
            
            # Extract links
            links = []
            for link in main_content.find_all('a', href=True):
                links.append({
                    "text": link.get_text(strip=True),
                    "url": link['href']
                })
            
            # Convert to text (simplified)
            content = main_content.get_text(separator='\n', strip=True)
            
            return content, links
        
        mock_to_thread.return_value = mock_process()
        
        content, links = await self.tool._extract_html_content(mock_html, extract_links=True)
        
        assert "Main Content" in content
        assert "Important paragraph" in content
        assert "console.log" not in content  # Script should be removed
        assert "color: red" not in content   # Style should be removed
        assert len(links) == 1
        assert links[0]["text"] == "Internal Link"
        assert links[0]["url"] == "/link1"


def run_content_tool_tests():
    """Run content retrieval tool tests manually"""
    print("Running ContentRetrievalTool tests...")
    
    test_instance = TestContentRetrievalTool()
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
        test_instance.test_format_content_for_llm()
        print("✅ Format content test passed")
    except Exception as e:
        print(f"❌ Format content test failed: {e}")
    
    # Async tests
    async def run_async_tests():
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_invalid_url()
            print("✅ Invalid URL test passed")
        except Exception as e:
            print(f"❌ Invalid URL test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_successful_html_content_retrieval()
            print("✅ HTML content retrieval test passed")
        except Exception as e:
            print(f"❌ HTML content retrieval test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_plain_text_content_retrieval()
            print("✅ Plain text content retrieval test passed")
        except Exception as e:
            print(f"❌ Plain text content retrieval test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_http_error_handling()
            print("✅ HTTP error handling test passed")
        except Exception as e:
            print(f"❌ HTTP error handling test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_unsupported_content_type()
            print("✅ Unsupported content type test passed")
        except Exception as e:
            print(f"❌ Unsupported content type test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_timeout_handling()
            print("✅ Timeout handling test passed")
        except Exception as e:
            print(f"❌ Timeout handling test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_content_length_truncation()
            print("✅ Content length truncation test passed")
        except Exception as e:
            print(f"❌ Content length truncation test failed: {e}")
        
        # Reset
        test_instance.setup_method()
        
        try:
            await test_instance.test_html_content_extraction()
            print("✅ HTML content extraction test passed")
        except Exception as e:
            print(f"❌ HTML content extraction test failed: {e}")
    
    asyncio.run(run_async_tests())
    print("ContentRetrievalTool tests completed!")


if __name__ == "__main__":
    run_content_tool_tests()