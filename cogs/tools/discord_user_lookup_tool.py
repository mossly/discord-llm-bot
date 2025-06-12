"""
Discord user lookup and discovery tool for finding users by name, display name, or partial matches
"""

from typing import Dict, Any, List, Optional
from .base_tool import BaseTool
import discord
import logging

logger = logging.getLogger(__name__)


class DiscordUserLookupTool(BaseTool):
    """Tool for discovering and looking up Discord users by various criteria"""
    
    def __init__(self, bot: discord.Client):
        super().__init__()
        self.bot = bot
    
    @property
    def name(self) -> str:
        return "lookup_discord_users"
    
    @property
    def description(self) -> str:
        return "Look up and discover Discord users by username, display name, or partial matches. Useful for finding user information before searching their messages or when you need to identify specific users in a server."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Username, display name, or partial name to search for (case-insensitive)"
                },
                "server_id": {
                    "type": "string",
                    "description": "Specific server/guild ID to search in (optional). If not provided, searches across all accessible servers."
                },
                "exact_match": {
                    "type": "boolean",
                    "description": "Whether to require exact matches only (default: false, allows partial matches)",
                    "default": False
                },
                "include_bots": {
                    "type": "boolean",
                    "description": "Whether to include bot accounts in results (default: false)",
                    "default": False
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of users to return (default: 10, max: 50)",
                    "default": 10
                }
            },
            "required": ["search_term"]
        }
    
    def _format_user_result(self, member: discord.Member) -> Dict[str, Any]:
        """Format member into result dictionary"""
        return {
            "user_id": str(member.id),
            "username": member.name,
            "display_name": member.display_name,
            "is_bot": member.bot,
            "avatar_url": str(member.avatar.url) if member.avatar else None,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            "created_at": member.created_at.isoformat(),
            "server": {
                "id": str(member.guild.id),
                "name": member.guild.name
            },
            "roles": [role.name for role in member.roles[1:] if role.name != "@everyone"],  # Exclude @everyone
            "top_role": member.top_role.name if member.top_role.name != "@everyone" else None,
            "status": str(member.status) if hasattr(member, 'status') else "unknown"
        }
    
    def _matches_criteria(self, member: discord.Member, search_term: str, 
                         exact_match: bool, include_bots: bool) -> tuple[bool, float]:
        """Check if member matches search criteria and return match score"""
        if not include_bots and member.bot:
            return False, 0.0
        
        search_lower = search_term.lower().strip()
        username_lower = member.name.lower()
        display_name_lower = member.display_name.lower()
        
        # Exact matches (highest score)
        if exact_match:
            if username_lower == search_lower or display_name_lower == search_lower:
                return True, 1.0
            return False, 0.0
        
        # Calculate match scores for fuzzy matching
        score = 0.0
        
        # Exact matches
        if username_lower == search_lower:
            score = 1.0
        elif display_name_lower == search_lower:
            score = 0.95
        # Starts with matches
        elif username_lower.startswith(search_lower):
            score = 0.8
        elif display_name_lower.startswith(search_lower):
            score = 0.75
        # Contains matches
        elif search_lower in username_lower:
            score = 0.6
        elif search_lower in display_name_lower:
            score = 0.55
        # Word boundary matches (useful for multi-word display names)
        elif any(word.startswith(search_lower) for word in display_name_lower.split()):
            score = 0.5
        
        return score > 0, score
    
    async def execute(self, search_term: str, server_id: Optional[str] = None,
                     exact_match: bool = False, include_bots: bool = False,
                     max_results: int = 10) -> Dict[str, Any]:
        """Execute Discord user lookup"""
        try:
            # Validate parameters
            if not search_term or len(search_term.strip()) < 1:
                return {
                    "success": False,
                    "error": "Search term must be at least 1 character long"
                }
            
            # Apply safety limits
            max_results = min(max_results, 50)
            
            results = []
            servers_searched = []
            
            # Search specific server
            if server_id:
                guild = self.bot.get_guild(int(server_id))
                if not guild:
                    return {
                        "success": False,
                        "error": f"Server with ID {server_id} not found or not accessible"
                    }
                
                servers_searched.append(guild.name)
                
                # Search through guild members
                for member in guild.members:
                    matches, score = self._matches_criteria(member, search_term, exact_match, include_bots)
                    if matches:
                        user_data = self._format_user_result(member)
                        user_data["match_score"] = score
                        results.append(user_data)
            
            # Search all accessible servers
            else:
                total_members_searched = 0
                for guild in self.bot.guilds:
                    servers_searched.append(guild.name)
                    guild_member_count = 0
                    
                    for member in guild.members:
                        guild_member_count += 1
                        total_members_searched += 1
                        
                        # Skip if we already have this user from another server
                        if any(result["user_id"] == str(member.id) for result in results):
                            continue
                            
                        matches, score = self._matches_criteria(member, search_term, exact_match, include_bots)
                        if matches:
                            user_data = self._format_user_result(member)
                            user_data["match_score"] = score
                            results.append(user_data)
                    
                    logger.debug(f"Searched {guild_member_count} members in guild '{guild.name}'")
                    
                    # Stop if we have enough results
                    if len(results) >= max_results * 2:  # Search a bit more for better sorting
                        break
                
                logger.info(f"User lookup completed:")
                logger.info(f"  Search term: '{search_term}' | Server: {server_id or 'All accessible'}")
                logger.info(f"  Members searched: {total_members_searched} | Servers: {len(servers_searched)}")
                logger.info(f"  Results: {len(results)} | Exact match: {exact_match}")
                if results and len(results) > 0:
                    logger.info(f"  Top match: {results[0]['username']} ({results[0]['display_name']}) - Score: {results[0].get('match_score', 'N/A')}")
            
            # Sort results by match score (highest first)
            results.sort(key=lambda x: x["match_score"], reverse=True)
            
            # Limit to requested number of results
            results = results[:max_results]
            
            # If no results found, provide helpful debugging info and suggestions
            message = f"Found {len(results)} user(s) matching '{search_term}' across {len(servers_searched)} server(s)"
            suggestions = []
            
            if len(results) == 0:
                # Try to find similar usernames for suggestions
                similar_users = []
                search_term_lower = search_term.lower()
                
                # Search for partial matches that didn't make the cut
                for guild in self.bot.guilds:
                    for member in guild.members:
                        if member.bot and not include_bots:
                            continue
                        
                        username_lower = member.name.lower()
                        display_name_lower = member.display_name.lower()
                        
                        # Find users with similar names (more relaxed matching)
                        similarity_score = 0
                        if any(char in username_lower for char in search_term_lower):
                            similarity_score += 1
                        if any(char in display_name_lower for char in search_term_lower):
                            similarity_score += 1
                        if len(set(search_term_lower) & set(username_lower)) >= min(2, len(search_term_lower) // 2):
                            similarity_score += 2
                        if len(set(search_term_lower) & set(display_name_lower)) >= min(2, len(search_term_lower) // 2):
                            similarity_score += 2
                        
                        if similarity_score > 0:
                            similar_users.append({
                                "username": member.name,
                                "display_name": member.display_name,
                                "user_id": str(member.id),
                                "similarity": similarity_score
                            })
                
                # Sort by similarity and take top 5
                similar_users.sort(key=lambda x: x["similarity"], reverse=True)
                suggestions = similar_users[:5]
                
                if suggestions:
                    user_suggestions = [f"{u['username']} ({u['display_name']})" for u in suggestions[:3]]
                    message += f". Did you mean one of these users: {', '.join(user_suggestions)}?"
            
            return {
                "success": True,
                "results": results,
                "search_term": search_term,
                "total_results": len(results),
                "suggestions": suggestions,
                "search_stats": {
                    "servers_searched": len(servers_searched),
                    "servers_searched_names": servers_searched[:5],  # Limit for readability
                    "exact_match_mode": exact_match,
                    "included_bots": include_bots,
                    "total_members_searched": total_members_searched if 'total_members_searched' in locals() else 0
                },
                "message": message
            }
            
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid parameter: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error in Discord user lookup: {e}")
            return {
                "success": False,
                "error": f"User lookup failed: {str(e)}"
            }
    
    def get_usage_summary(self) -> str:
        """Get a summary of tool usage for monitoring"""
        return f"DiscordUserLookup: {self.usage_count} lookups, {self.error_count} errors"