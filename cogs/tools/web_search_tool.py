"""
Web search tool implementation
"""

from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
from duckduckgo_search import DDGS
import asyncio
import os
import logging
import aiohttp

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Tool for searching the web"""
    
    def __init__(self, use_ddg: bool = True, exa_api_key: Optional[str] = None):
        super().__init__()
        self.use_ddg = use_ddg
        self.exa_api_key = exa_api_key or os.getenv("EXA_API_KEY")
        self.proxy = os.getenv("DUCK_PROXY")
    
    @property
    def name(self) -> str:
        return "search_web"
    
    @property
    def description(self) -> str:
        return "Search the web for current information. Use this when you need up-to-date information or facts about any topic."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5, max: 10)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Execute web search"""
        # Limit max results
        max_results = min(max_results, 10)
        
        if self.use_ddg:
            return await self._search_ddg(query, max_results)
        elif self.exa_api_key:
            return await self._search_exa(query, max_results)
        else:
            return {
                "error": "No search provider configured",
                "success": False
            }
    
    async def _search_ddg(self, query: str, max_results: int) -> Dict[str, Any]:
        """Search using DuckDuckGo with rate limit handling"""
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            def _ddg_search():
                try:
                    ddgs = DDGS(proxy=self.proxy) if self.proxy else DDGS()
                    results = list(ddgs.text(query.strip('"').strip(), max_results=max_results))
                    return results
                except Exception as e:
                    # Let the outer handler deal with the exception
                    raise e
            
            try:
                results = await asyncio.to_thread(_ddg_search)
                if results is not None:
                    break
                    
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check for rate limiting indicators
                if any(indicator in error_msg for indicator in ['ratelimit', 'rate limit', '202', 'backoff']):
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(f"DDG rate limit detected (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"DDG rate limited after {max_retries} attempts: {e}")
                        return {
                            "error": f"Search rate limited after {max_retries} attempts. Please try again later.",
                            "success": False
                        }
                
                # Check for timeout/connection issues
                elif any(indicator in error_msg for indicator in ['timeout', 'connection', 'network']):
                    if attempt < max_retries - 1:
                        delay = base_delay * (attempt + 1)  # Linear backoff for timeouts: 1s, 2s, 3s
                        logger.warning(f"DDG connection issue (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"DDG connection failed after {max_retries} attempts: {e}")
                        return {
                            "error": f"Search connection failed after {max_retries} attempts. Please try again later.",
                            "success": False
                        }
                
                # Other errors - don't retry
                else:
                    logger.error(f"DuckDuckGo search error: {e}")
                    return {
                        "error": f"Search failed: {str(e)}",
                        "success": False
                    }
        else:
            # Should not reach here, but safety net
            return {
                "error": "Search failed after retries",
                "success": False
            }
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        
        return {
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "success": True
        }
    
    async def _search_exa(self, query: str, max_results: int) -> Dict[str, Any]:
        """Search using Exa API"""
        if not self.exa_api_key:
            return {
                "error": "Exa API key not configured",
                "success": False
            }
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "x-api-key": self.exa_api_key,
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "query": query,
                    "num_results": max_results,
                    "type": "neural"
                }
                
                async with session.post(
                    "https://api.exa.ai/search",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        formatted_results = []
                        for result in results:
                            formatted_results.append({
                                "title": result.get("title", ""),
                                "url": result.get("url", ""),
                                "snippet": result.get("snippet", "")
                            })
                        
                        return {
                            "query": query,
                            "results": formatted_results,
                            "count": len(formatted_results),
                            "success": True
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "error": f"Exa API error: {error_text}",
                            "success": False
                        }
        except Exception as e:
            logger.error(f"Exa search error: {e}")
            return {
                "error": f"Search failed: {str(e)}",
                "success": False
            }
    
    def format_results_for_llm(self, results: Dict[str, Any]) -> str:
        """Format search results for LLM consumption"""
        if not results.get("success"):
            return f"Search failed: {results.get('error', 'Unknown error')}"
        
        if not results.get("results"):
            return "No search results found."
        
        formatted = f"Web search results for '{results['query']}':\n\n"
        
        for i, result in enumerate(results["results"], 1):
            formatted += f"{i}. {result['title']}\n"
            formatted += f"   URL: {result['url']}\n"
            formatted += f"   {result['snippet']}\n\n"
        
        return formatted.strip()