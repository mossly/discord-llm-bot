"""
Character Sheet Tool - LLM tool for managing RPG character sheets
Allows the LLM to view and modify player stats, inventory, and custom attributes
"""

from typing import Dict, Any, Optional
from .base_tool import BaseTool
import logging

logger = logging.getLogger(__name__)


class CharacterSheetTool(BaseTool):
    """Tool for managing RPG character sheets"""

    def __init__(self, character_manager):
        super().__init__()
        self.character_manager = character_manager

    @property
    def name(self) -> str:
        return "character_sheet"

    @property
    def description(self) -> str:
        return """Manage RPG character sheets for users. Use this tool to view and modify character stats like HP, MP, XP, Level, attributes, gold, and inventory.

Operations:
- "view": Get the full character sheet
- "modify_stat": Change a stat by a delta (e.g., take 10 damage = modify hp by -10)
- "set_stat": Set a stat to a specific value
- "add_item": Add an item to inventory
- "remove_item": Remove an item from inventory
- "set_name": Set the character's name
- "reset": Reset the character to default values

Stats: hp, max_hp, mp, max_mp, xp, level, gold, strength (str), dexterity (dex), constitution (con), intelligence (int), wisdom (wis), charisma (cha)

Custom stats can also be used - they will be stored and retrieved automatically."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["view", "modify_stat", "set_stat", "add_item", "remove_item", "set_name", "reset"],
                    "description": "The operation to perform on the character sheet"
                },
                "stat": {
                    "type": "string",
                    "description": "The stat to modify (for modify_stat and set_stat operations). Examples: hp, mp, xp, level, gold, str, dex, con, int, wis, cha, or any custom stat name"
                },
                "value": {
                    "type": "integer",
                    "description": "The value for set_stat operations (absolute value to set)"
                },
                "delta": {
                    "type": "integer",
                    "description": "The change amount for modify_stat operations (positive to add, negative to subtract)"
                },
                "item": {
                    "type": "string",
                    "description": "The item name for add_item/remove_item operations"
                },
                "name": {
                    "type": "string",
                    "description": "The character name for set_name operation"
                }
            },
            "required": ["operation"]
        }

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute character sheet operation"""
        try:
            operation = kwargs.get("operation")
            user_id = kwargs.get("user_id")
            channel_id = kwargs.get("channel_id")

            if not user_id:
                return {
                    "success": False,
                    "error": "user_id is required"
                }

            # Convert to int if needed
            user_id = int(user_id)
            if channel_id:
                channel_id = int(channel_id)

            if operation == "view":
                return await self._view_character(user_id, channel_id)

            elif operation == "modify_stat":
                stat = kwargs.get("stat")
                delta = kwargs.get("delta", 0)
                if not stat:
                    return {"success": False, "error": "stat is required for modify_stat operation"}
                return await self._modify_stat(user_id, channel_id, stat, delta)

            elif operation == "set_stat":
                stat = kwargs.get("stat")
                value = kwargs.get("value")
                if not stat:
                    return {"success": False, "error": "stat is required for set_stat operation"}
                if value is None:
                    return {"success": False, "error": "value is required for set_stat operation"}
                return await self._set_stat(user_id, channel_id, stat, value)

            elif operation == "add_item":
                item = kwargs.get("item")
                if not item:
                    return {"success": False, "error": "item is required for add_item operation"}
                return await self._add_item(user_id, channel_id, item)

            elif operation == "remove_item":
                item = kwargs.get("item")
                if not item:
                    return {"success": False, "error": "item is required for remove_item operation"}
                return await self._remove_item(user_id, channel_id, item)

            elif operation == "set_name":
                name = kwargs.get("name")
                if not name:
                    return {"success": False, "error": "name is required for set_name operation"}
                return await self._set_name(user_id, channel_id, name)

            elif operation == "reset":
                return await self._reset_character(user_id, channel_id)

            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

        except Exception as e:
            logger.error(f"Error in character sheet tool: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Character sheet operation failed: {str(e)}"
            }

    async def _view_character(self, user_id: int, channel_id: Optional[int]) -> Dict[str, Any]:
        """View the character sheet"""
        character = await self.character_manager.get_or_create_character(user_id, channel_id)
        return {
            "success": True,
            "operation": "view",
            "character": character.to_dict()
        }

    async def _modify_stat(self, user_id: int, channel_id: Optional[int], stat: str, delta: int) -> Dict[str, Any]:
        """Modify a stat by delta"""
        character = await self.character_manager.modify_stat(user_id, channel_id, stat, delta)
        if character:
            stat_lower = stat.lower()
            # Get the new value
            new_value = getattr(character, stat_lower, character.get_custom_stat(stat_lower))

            return {
                "success": True,
                "operation": "modify_stat",
                "stat": stat,
                "delta": delta,
                "new_value": new_value,
                "character": character.to_dict(),
                "message": f"{stat} {'increased' if delta > 0 else 'decreased'} by {abs(delta)} to {new_value}"
            }
        return {"success": False, "error": "Failed to modify stat"}

    async def _set_stat(self, user_id: int, channel_id: Optional[int], stat: str, value: int) -> Dict[str, Any]:
        """Set a stat to specific value"""
        character = await self.character_manager.set_stat(user_id, channel_id, stat, value)
        if character:
            stat_lower = stat.lower()
            new_value = getattr(character, stat_lower, character.get_custom_stat(stat_lower))

            return {
                "success": True,
                "operation": "set_stat",
                "stat": stat,
                "value": new_value,
                "character": character.to_dict(),
                "message": f"{stat} set to {new_value}"
            }
        return {"success": False, "error": "Failed to set stat"}

    async def _add_item(self, user_id: int, channel_id: Optional[int], item: str) -> Dict[str, Any]:
        """Add item to inventory"""
        character = await self.character_manager.get_or_create_character(user_id, channel_id)
        character.add_item(item)
        await self.character_manager.update_character(character)

        return {
            "success": True,
            "operation": "add_item",
            "item": item,
            "inventory": character.get_inventory_list(),
            "message": f"Added '{item}' to inventory"
        }

    async def _remove_item(self, user_id: int, channel_id: Optional[int], item: str) -> Dict[str, Any]:
        """Remove item from inventory"""
        character = await self.character_manager.get_or_create_character(user_id, channel_id)

        if character.remove_item(item):
            await self.character_manager.update_character(character)
            return {
                "success": True,
                "operation": "remove_item",
                "item": item,
                "inventory": character.get_inventory_list(),
                "message": f"Removed '{item}' from inventory"
            }
        else:
            return {
                "success": False,
                "error": f"Item '{item}' not found in inventory",
                "inventory": character.get_inventory_list()
            }

    async def _set_name(self, user_id: int, channel_id: Optional[int], name: str) -> Dict[str, Any]:
        """Set character name"""
        character = await self.character_manager.get_or_create_character(user_id, channel_id)
        old_name = character.name
        character.name = name
        await self.character_manager.update_character(character)

        return {
            "success": True,
            "operation": "set_name",
            "old_name": old_name,
            "new_name": name,
            "message": f"Character renamed from '{old_name}' to '{name}'"
        }

    async def _reset_character(self, user_id: int, channel_id: Optional[int]) -> Dict[str, Any]:
        """Reset character to defaults"""
        # Get existing character to delete
        existing = await self.character_manager.get_character(user_id, channel_id)
        if existing and existing.id:
            await self.character_manager.delete_character(existing.id)

        # Create fresh character
        character = await self.character_manager.get_or_create_character(user_id, channel_id)

        return {
            "success": True,
            "operation": "reset",
            "character": character.to_dict(),
            "message": "Character has been reset to default values"
        }

    def format_results_for_llm(self, result: Dict[str, Any]) -> str:
        """Format character sheet results for LLM consumption"""
        if not result.get("success"):
            return f"Character sheet operation failed: {result.get('error', 'Unknown error')}"

        operation = result.get("operation", "unknown")

        if operation == "view":
            char = result.get("character", {})
            lines = [
                f"**{char.get('name', 'Adventurer')}** (Level {char.get('level', 1)})",
                f"HP: {char.get('hp', 0)}/{char.get('max_hp', 0)} | MP: {char.get('mp', 0)}/{char.get('max_mp', 0)}",
                f"XP: {char.get('xp', 0)} | Gold: {char.get('gold', 0)}",
                "",
                "**Attributes:**",
                f"STR: {char.get('strength', 10)} | DEX: {char.get('dexterity', 10)} | CON: {char.get('constitution', 10)}",
                f"INT: {char.get('intelligence', 10)} | WIS: {char.get('wisdom', 10)} | CHA: {char.get('charisma', 10)}",
            ]

            inventory = char.get('inventory', [])
            if inventory:
                lines.append("")
                lines.append(f"**Inventory:** {', '.join(inventory)}")

            custom = char.get('custom_stats', {})
            if custom:
                lines.append("")
                lines.append(f"**Custom Stats:** {', '.join(f'{k}: {v}' for k, v in custom.items())}")

            return "\n".join(lines)

        else:
            return result.get("message", f"Operation '{operation}' completed successfully")
