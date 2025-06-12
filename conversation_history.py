import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

class ConversationHistoryManager:
    def __init__(self, history_file: str = "/data/conversation_history.json", max_history_size: int = 100000):
        # Ensure /data directory exists
        os.makedirs("/data", exist_ok=True)
        self.history_file = history_file
        self.max_history_size = max_history_size  # Max number of conversations to store
        self.conversations = self._load_conversations()
        self.lock = threading.Lock()  # Thread safety for concurrent access
        
    def _load_conversations(self) -> Dict:
        """Load conversation history from JSON file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data.get('conversations', []))} conversations from history")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading conversation history: {e}")
                return {"conversations": [], "index": {}}
        return {"conversations": [], "index": {}}
    
    def _save_conversations(self):
        """Save conversation history to JSON file"""
        try:
            with self.lock:
                # Limit the size of stored conversations
                if len(self.conversations["conversations"]) > self.max_history_size:
                    # Keep only the most recent conversations
                    self.conversations["conversations"] = self.conversations["conversations"][-self.max_history_size:]
                    # Rebuild index
                    self._rebuild_index()
                
                with open(self.history_file, 'w') as f:
                    json.dump(self.conversations, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving conversation history: {e}")
    
    def _rebuild_index(self):
        """Rebuild the user index after pruning conversations"""
        self.conversations["index"] = defaultdict(list)
        for i, conv in enumerate(self.conversations["conversations"]):
            user_id = conv["user_id"]
            if user_id not in self.conversations["index"]:
                self.conversations["index"][user_id] = []
            self.conversations["index"][user_id].append(i)
    
    def add_conversation(self, user_id: str, user_name: str, user_message: str, 
                        bot_response: str, model: str, server_id: Optional[str] = None,
                        server_name: Optional[str] = None, channel_id: Optional[str] = None,
                        channel_name: Optional[str] = None, thread_id: Optional[str] = None,
                        cost: Optional[float] = None, input_tokens: Optional[int] = None,
                        output_tokens: Optional[int] = None):
        """Add a conversation to the history"""
        conversation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "user_name": user_name,
            "user_message": user_message,
            "bot_response": bot_response,
            "model": model,
            "server_id": server_id,
            "server_name": server_name,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "thread_id": thread_id,
            "cost": cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }
        
        with self.lock:
            # Add to conversations list
            conv_index = len(self.conversations["conversations"])
            self.conversations["conversations"].append(conversation)
            
            # Update user index
            if "index" not in self.conversations:
                self.conversations["index"] = {}
            if user_id not in self.conversations["index"]:
                self.conversations["index"][user_id] = []
            self.conversations["index"][user_id].append(conv_index)
        
        self._save_conversations()
        logger.info(f"Added conversation for user {user_id} ({user_name}) using model {model}")
    
    def search_user_conversations(self, user_id: str, query: Optional[str] = None, 
                                 limit: int = 50, offset: int = 0) -> List[Dict]:
        """Search conversations for a specific user"""
        with self.lock:
            # Get conversation indices for this user
            user_indices = self.conversations["index"].get(user_id, [])
            
            # Get conversations in reverse chronological order
            user_conversations = []
            for idx in reversed(user_indices):
                if idx < len(self.conversations["conversations"]):
                    conv = self.conversations["conversations"][idx]
                    
                    # Apply search query if provided
                    if query:
                        query_lower = query.lower()
                        if (query_lower in conv["user_message"].lower() or 
                            query_lower in conv["bot_response"].lower()):
                            user_conversations.append(conv)
                    else:
                        user_conversations.append(conv)
            
            # Apply pagination
            start = offset
            end = offset + limit
            return user_conversations[start:end]
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get statistics for a specific user"""
        with self.lock:
            user_indices = self.conversations["index"].get(user_id, [])
            
            if not user_indices:
                return {
                    "total_conversations": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "first_conversation": None,
                    "last_conversation": None
                }
            
            total_cost = 0.0
            total_tokens = 0
            first_conv = None
            last_conv = None
            
            for idx in user_indices:
                if idx < len(self.conversations["conversations"]):
                    conv = self.conversations["conversations"][idx]
                    
                    # Track cost
                    if conv.get("cost"):
                        total_cost += conv["cost"]
                    
                    # Track tokens
                    if conv.get("input_tokens"):
                        total_tokens += conv["input_tokens"]
                    if conv.get("output_tokens"):
                        total_tokens += conv["output_tokens"]
                    
                    # Track first and last conversations
                    if not first_conv or conv["timestamp"] < first_conv["timestamp"]:
                        first_conv = conv
                    if not last_conv or conv["timestamp"] > last_conv["timestamp"]:
                        last_conv = conv
            
            return {
                "total_conversations": len(user_indices),
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "first_conversation": first_conv["timestamp"] if first_conv else None,
                "last_conversation": last_conv["timestamp"] if last_conv else None
            }
    
    def search_all_conversations(self, query: str, limit: int = 50, offset: int = 0) -> List[Tuple[Dict, str]]:
        """Search all conversations regardless of user"""
        with self.lock:
            matching_conversations = []
            query_lower = query.lower()
            
            for conv in reversed(self.conversations["conversations"]):
                if (query_lower in conv["user_message"].lower() or 
                    query_lower in conv["bot_response"].lower()):
                    matching_conversations.append(conv)
            
            # Apply pagination
            start = offset
            end = offset + limit
            return matching_conversations[start:end]
    
    def clear_user_history(self, user_id: str) -> int:
        """Clear all conversation history for a specific user"""
        with self.lock:
            user_indices = self.conversations["index"].get(user_id, [])
            count = len(user_indices)
            
            if count > 0:
                # Remove conversations (in reverse order to maintain indices)
                for idx in sorted(user_indices, reverse=True):
                    if idx < len(self.conversations["conversations"]):
                        self.conversations["conversations"].pop(idx)
                
                # Rebuild the entire index
                self._rebuild_index()
                self._save_conversations()
                
            logger.info(f"Cleared {count} conversations for user {user_id}")
            return count