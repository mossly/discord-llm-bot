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
        return "Search through previous conversation history to find relevant context from past interactions. Use this to help with follow-up questions or when context from previous conversations would be helpful."
    
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
                    "description": "User ID to search conversations for (required)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return (default: 10, max: 25)",
                    "default": 10
                }
            },
            "required": ["query", "user_id"]
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
    
    def get_usage_summary(self) -> str:
        """Get a summary of tool usage for monitoring"""
        return f"ConversationSearch: {self.usage_count} searches, {self.error_count} errors"