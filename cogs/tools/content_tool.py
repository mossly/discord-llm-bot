"""
Content retrieval tool for fetching and extracting web content
"""

from typing import Dict, Any, Optional, List
from .base_tool import BaseTool
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import logging
import re
from urllib.parse import urlparse
import html2text

logger = logging.getLogger(__name__)


class ContentRetrievalTool(BaseTool):
    """Tool for retrieving and extracting content from web pages"""
    
    def __init__(self, timeout: int = 10, max_content_length: int = 50000):
        super().__init__()
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.body_width = 0  # Don't wrap text
    
    @property
    def name(self) -> str:
        return "get_contents"
    
    @property
    def description(self) -> str:
        return "Retrieve and extract the main content from a web page. Use this to get detailed information from a specific URL."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to retrieve content from"
                },
                "extract_links": {
                    "type": "boolean",
                    "description": "Whether to extract and include links from the page",
                    "default": False
                }
            },
            "required": ["url"]
        }
    
    async def execute(self, url: str, extract_links: bool = False) -> Dict[str, Any]:
        """Retrieve content from URL"""
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {
                    "error": "Invalid URL format",
                    "success": False
                }
        except Exception:
            return {
                "error": "Invalid URL",
                "success": False
            }
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(
                    url, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        return {
                            "error": f"HTTP {response.status}: {response.reason}",
                            "success": False
                        }
                    
                    # Check content type
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type and 'text/plain' not in content_type:
                        return {
                            "error": f"Unsupported content type: {content_type}",
                            "success": False
                        }
                    
                    # Read content with size limit
                    content = await response.text()
                    if len(content) > self.max_content_length * 2:  # Allow some overhead for HTML
                        content = content[:self.max_content_length * 2]
                    
                    # Extract content
                    if 'text/plain' in content_type:
                        extracted_content = content[:self.max_content_length]
                        links = []
                    else:
                        extracted_content, links = await self._extract_html_content(
                            content, extract_links
                        )
                    
                    # Get page metadata
                    title = await self._extract_title(content, content_type)
                    
                    result = {
                        "url": url,
                        "title": title,
                        "content": extracted_content[:self.max_content_length],
                        "content_length": len(extracted_content),
                        "truncated": len(extracted_content) > self.max_content_length,
                        "success": True
                    }
                    
                    if extract_links and links:
                        result["links"] = links[:50]  # Limit number of links
                    
                    return result
                    
        except asyncio.TimeoutError:
            return {
                "error": f"Timeout after {self.timeout} seconds",
                "success": False
            }
        except Exception as e:
            logger.error(f"Content retrieval error for {url}: {e}")
            return {
                "error": f"Failed to retrieve content: {str(e)}",
                "success": False
            }
    
    async def _extract_html_content(
        self, 
        html: str, 
        extract_links: bool
    ) -> tuple[str, List[Dict[str, str]]]:
        """Extract main content from HTML"""
        def _process():
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Try to find main content areas
            main_content = None
            for selector in ['main', 'article', '[role="main"]', '#content', '.content']:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            # If no main content found, use body
            if not main_content:
                main_content = soup.find('body')
            
            if not main_content:
                main_content = soup
            
            # Extract links if requested
            links = []
            if extract_links:
                for link in main_content.find_all('a', href=True):
                    href = link['href']
                    text = link.get_text(strip=True)
                    if href and text:
                        links.append({
                            "text": text[:100],  # Limit link text length
                            "url": href
                        })
            
            # Convert to markdown
            html_str = str(main_content)
            markdown_content = self.html_converter.handle(html_str)
            
            # Clean up excessive whitespace
            markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
            markdown_content = markdown_content.strip()
            
            return markdown_content, links
        
        return await asyncio.to_thread(_process)
    
    async def _extract_title(self, content: str, content_type: str) -> str:
        """Extract title from content"""
        if 'text/plain' in content_type:
            # For plain text, use first line as title
            first_line = content.split('\n')[0].strip()
            return first_line[:100] if first_line else "Untitled"
        
        def _get_title():
            soup = BeautifulSoup(content, 'html.parser')
            
            # Try different title sources
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                return title_tag.string.strip()
            
            # Try meta property og:title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                return og_title['content'].strip()
            
            # Try h1
            h1 = soup.find('h1')
            if h1:
                return h1.get_text(strip=True)
            
            return "Untitled"
        
        title = await asyncio.to_thread(_get_title)
        return title[:200]  # Limit title length
    
    def format_content_for_llm(self, result: Dict[str, Any]) -> str:
        """Format content for LLM consumption"""
        if not result.get("success"):
            return f"Content retrieval failed: {result.get('error', 'Unknown error')}"
        
        formatted = f"Content from {result['url']}:\n"
        formatted += f"Title: {result['title']}\n\n"
        formatted += result['content']
        
        if result.get('truncated'):
            formatted += f"\n\n[Content truncated at {result['content_length']} characters]"
        
        if result.get('links'):
            formatted += "\n\nExtracted links:\n"
            for i, link in enumerate(result['links'][:10], 1):
                formatted += f"{i}. {link['text']}: {link['url']}\n"
        
        return formatted