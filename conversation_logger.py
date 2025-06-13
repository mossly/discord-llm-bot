"""
Conversation logging utilities for Discord LLM bot
Handles logging of user-bot conversations for history and analytics
"""

import logging
import discord
from typing import Optional
from conversation_history import ConversationHistoryManager

logger = logging.getLogger(__name__)


class ConversationLogger:
    """Handles logging of conversations between users and the bot"""
    
    def __init__(self):
        self.conversation_history = ConversationHistoryManager()
    
    async def log_conversation(
        self,
        user_id: str,
        user_message: str,
        bot_response: str,
        model: str,
        channel: Optional[discord.TextChannel] = None,
        interaction: Optional[discord.Interaction] = None,
        username: Optional[str] = None,
        cost: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> bool:
        """
        Log a conversation to the history system
        
        Args:
            user_id: Discord user ID
            user_message: The user's original message
            bot_response: The bot's response (cleaned of footnotes)
            model: Model used for the response
            channel: Discord channel (if available)
            interaction: Discord interaction (if available) 
            username: Username (if not derivable from interaction)
            cost: API cost for this conversation
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            
        Returns:
            True if logging was successful, False otherwise
        """
        try:
            # Extract context information
            context = self._extract_context_info(channel, interaction)
            
            # Determine username
            final_username = self._determine_username(user_id, username, interaction)
            
            # Log the conversation
            self.conversation_history.add_conversation(
                user_id=user_id,
                user_name=final_username,
                user_message=user_message,
                bot_response=bot_response,
                model=model,
                server_id=context["server_id"],
                server_name=context["server_name"],
                channel_id=context["channel_id"],
                channel_name=context["channel_name"],
                thread_id=context["thread_id"],
                cost=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            logger.debug(
                f"Logged conversation for user {user_id} in {context['channel_name']} "
                f"using {model} (cost: ${cost:.4f})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to log conversation for user {user_id}: {e}")
            return False
    
    def _extract_context_info(
        self, 
        channel: Optional[discord.TextChannel], 
        interaction: Optional[discord.Interaction]
    ) -> dict:
        """Extract server and channel context information"""
        context = {
            "server_id": None,
            "server_name": None,
            "channel_id": None,
            "channel_name": "Unknown",
            "thread_id": None
        }
        
        # Try to get context from channel first
        if channel:
            context["channel_id"] = str(channel.id)
            
            if hasattr(channel, 'name') and channel.name:
                context["channel_name"] = channel.name
            elif isinstance(channel, discord.DMChannel):
                context["channel_name"] = "DM"
            elif isinstance(channel, discord.Thread):
                context["channel_name"] = channel.name
                context["thread_id"] = str(channel.id)
            
            if channel.guild:
                context["server_id"] = str(channel.guild.id)
                context["server_name"] = channel.guild.name
        
        # Fall back to interaction if no channel
        elif interaction and hasattr(interaction, 'channel') and interaction.channel:
            channel = interaction.channel
            context["channel_id"] = str(channel.id)
            
            if hasattr(channel, 'name'):
                context["channel_name"] = channel.name
            
            if hasattr(interaction, 'guild') and interaction.guild:
                context["server_id"] = str(interaction.guild.id)
                context["server_name"] = interaction.guild.name
        
        return context
    
    def _determine_username(
        self, 
        user_id: str, 
        username: Optional[str], 
        interaction: Optional[discord.Interaction]
    ) -> str:
        """Determine the username to use for logging"""
        # Use provided username if available
        if username:
            return username
        
        # Try to get from interaction
        if interaction and hasattr(interaction, 'user') and interaction.user:
            return interaction.user.name
        
        # Fallback to user ID
        return f"User_{user_id}"
    
    def get_conversation_history_manager(self) -> ConversationHistoryManager:
        """Get the underlying conversation history manager"""
        return self.conversation_history


# Create a global instance for easy access
conversation_logger = ConversationLogger()


# Export for easy importing
__all__ = [
    'ConversationLogger',
    'conversation_logger'
]