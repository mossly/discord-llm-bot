"""
Conversation search tool for LLMs to search through conversation history
"""

from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
from conversation_history import ConversationHistoryManager
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationSearchTool(BaseTool):
    """Tool for searching conversation history"""
    
    def __init__(self):
        super().__init__()
        self.history_manager = ConversationHistoryManager()
    
    @property
    def name(self) -> str:
        return "search_conversations"
    
    @property
    def description(self) -> str:
        return "Search through your previous conversation history to find relevant context from past interactions. Use this to help with follow-up questions or when context from previous conversations would be helpful. Note: You can only search your own conversation history for privacy."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find in conversation history (searches both user messages and bot responses)"
                },
                "user_id": {
                    "type": "string",
                    "description": "User ID to search conversations for (automatically set to your ID for security)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return (default: 10, max: 25)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Execute conversation search"""
        try:
            # Validate parameters
            if not query or len(query.strip()) < 2:
                return {
                    "success": False,
                    "error": "Query must be at least 2 characters long"
                }
            
            if not user_id:
                return {
                    "success": False,
                    "error": "user_id is required"
                }
            
            # Limit results
            limit = min(limit, 25)
            
            # Search specific user's conversations
            conversations = self.history_manager.search_user_conversations(
                user_id=user_id,
                query=query,
                limit=limit
            )
            search_type = f"user {user_id}"
            
            if not conversations:
                return {
                    "success": True,
                    "results": [],
                    "message": f"No conversations found matching '{query}' for {search_type}",
                    "query": query,
                    "search_type": search_type
                }
            
            # Format results for LLM consumption
            formatted_results = []
            for conv in conversations:
                # Parse timestamp for better readability
                timestamp = datetime.fromisoformat(conv["timestamp"])
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M UTC")
                
                result = {
                    "timestamp": formatted_time,
                    "user_id": conv["user_id"],
                    "user_name": conv["user_name"],
                    "user_message": conv["user_message"],
                    "bot_response": conv["bot_response"],
                    "model": conv["model"]
                }
                
                # Add context info if available
                if conv.get("server_name"):
                    result["server"] = conv["server_name"]
                if conv.get("channel_name"):
                    result["channel"] = conv["channel_name"]
                if conv.get("cost"):
                    result["cost"] = conv["cost"]
                if conv.get("input_tokens") or conv.get("output_tokens"):
                    result["tokens"] = {
                        "input": conv.get("input_tokens", 0),
                        "output": conv.get("output_tokens", 0)
                    }
                
                formatted_results.append(result)
            
            # Log search summary
            logger.info(f"Conversation search completed:")
            logger.info(f"  Query: '{query}' | User: {user_id}")
            logger.info(f"  Results: {len(conversations)}/{limit}")
            if formatted_results:
                # Log first result preview
                first = formatted_results[0]
                logger.info(f"  First result: {first['timestamp']} - User: '{first['user_message'][:50]}...'")
            
            return {
                "success": True,
                "results": formatted_results,
                "message": f"Found {len(conversations)} conversation(s) matching '{query}' for {search_type}",
                "query": query,
                "search_type": search_type,
                "total_results": len(conversations)
            }
            
        except Exception as e:
            logger.error(f"Error in conversation search tool: {e}")
            return {
                "success": False,
                "error": f"Failed to search conversations: {str(e)}"
            }
    
    def format_results_for_llm(self, result: Dict[str, Any]) -> str:
        """Format search results in a readable way for LLM consumption"""
        if not result.get("success"):
            return f"Search failed: {result.get('error', 'Unknown error')}"
        
        results = result.get("results", [])
        if not results:
            query = result.get("query", "")
            search_type = result.get("search_type", "")
            return f"No conversations found matching '{query}' for {search_type}."
        
        # Format each conversation in a readable way
        formatted_conversations = []
        for i, conv in enumerate(results, 1):
            formatted_conv = f"**Conversation {i}** ({conv['timestamp']}):\n"
            formatted_conv += f"User ({conv['user_name']}): {conv['user_message']}\n"
            formatted_conv += f"Bot ({conv['model']}): {conv['bot_response']}\n"
            
            if conv.get('server'):
                formatted_conv += f"Server: {conv['server']}\n"
            if conv.get('channel'):
                formatted_conv += f"Channel: {conv['channel']}\n"
            if conv.get('cost'):
                formatted_conv += f"Cost: ${conv['cost']:.4f}\n"
            
            formatted_conversations.append(formatted_conv)
        
        header = f"Found {len(results)} conversation(s) matching '{result.get('query', '')}'"
        return header + "\n\n" + "\n---\n".join(formatted_conversations)
    
    def get_usage_summary(self) -> str:
        """Get a summary of tool usage for monitoring"""
        return f"ConversationSearch: {self.usage_count} searches, {self.error_count} errors"