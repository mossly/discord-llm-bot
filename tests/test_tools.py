#!/usr/bin/env python3
"""
Simple test script for tool calling system
"""
import asyncio
import logging
from cogs.tools import ToolRegistry, WebSearchTool, ContentRetrievalTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_tools():
    """Test the tool system"""
    print("Testing Tool System...")
    
    # Create registry
    registry = ToolRegistry()
    
    # Create and register tools
    web_search = WebSearchTool(use_ddg=True)
    content_tool = ContentRetrievalTool()
    
    registry.register(web_search, enabled=True)
    registry.register(content_tool, enabled=True)
    
    print(f"Registered {len(registry.list_tools())} tools")
    
    # Test tool schemas
    schemas = registry.get_all_schemas()
    print(f"Generated {len(schemas)} tool schemas")
    
    for schema in schemas:
        print(f"- {schema['function']['name']}: {schema['function']['description']}")
    
    # Test web search tool
    print("\nTesting web search...")
    try:
        result = await registry.execute_tool("search_web", query="Python programming", max_results=3)
        if result.get("success"):
            print(f"Search successful: {len(result.get('results', []))} results")
        else:
            print(f"Search failed: {result.get('error')}")
    except Exception as e:
        print(f"Search error: {e}")
    
    # Test content retrieval tool
    print("\nTesting content retrieval...")
    try:
        result = await registry.execute_tool("get_contents", url="https://www.python.org")
        if result.get("success"):
            print(f"Content retrieved: {len(result.get('content', ''))} characters")
            print(f"Title: {result.get('title', 'No title')}")
        else:
            print(f"Content retrieval failed: {result.get('error')}")
    except Exception as e:
        print(f"Content error: {e}")
    
    # Test tool stats
    print("\nTool Statistics:")
    stats = registry.get_stats()
    for tool_name, tool_stats in stats.items():
        print(f"- {tool_name}: Used {tool_stats['usage_count']} times, {tool_stats['error_count']} errors")
    
    print("Tool testing complete!")

if __name__ == "__main__":
    asyncio.run(test_tools())