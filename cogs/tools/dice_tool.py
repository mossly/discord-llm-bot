"""
Dice rolling tool implementation for random number generation and decision making
"""

from typing import Dict, Any, List
from .base_tool import BaseTool
import random
import logging

logger = logging.getLogger(__name__)


class DiceTool(BaseTool):
    """Tool for rolling dice with various configurations"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "roll_dice"
    
    @property
    def description(self) -> str:
        return "Roll dice for random number generation, decision making, or roleplaying. Supports standard RPG dice (d4, d6, d8, d10, d12, d20, d100) and custom configurations."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sides": {
                    "type": "integer",
                    "description": "Number of sides on the dice (minimum: 2, maximum: 1000). Common values: 4, 6, 8, 10, 12, 20, 100",
                    "minimum": 2,
                    "maximum": 1000
                },
                "count": {
                    "type": "integer",
                    "description": "Number of dice to roll (default: 1, maximum: 10)",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 10
                },
                "modifier": {
                    "type": "integer",
                    "description": "Modifier to add to the total result (can be negative, default: 0)",
                    "default": 0
                }
            },
            "required": ["sides"]
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute dice roll with given parameters"""
        try:
            sides = kwargs.get("sides")
            count = kwargs.get("count", 1)
            modifier = kwargs.get("modifier", 0)
            
            # Validate parameters
            if not isinstance(sides, int) or sides < 2 or sides > 1000:
                return {
                    "success": False,
                    "error": "Sides must be an integer between 2 and 1000"
                }
            
            if not isinstance(count, int) or count < 1 or count > 10:
                return {
                    "success": False,
                    "error": "Count must be an integer between 1 and 10"
                }
            
            if not isinstance(modifier, int):
                return {
                    "success": False,
                    "error": "Modifier must be an integer"
                }
            
            # Roll the dice
            rolls = []
            for _ in range(count):
                roll = random.randint(1, sides)
                rolls.append(roll)
            
            # Calculate total
            total_before_modifier = sum(rolls)
            final_total = total_before_modifier + modifier
            
            # Format the result string
            if count == 1:
                if modifier == 0:
                    result_text = f"Rolling 1d{sides}: {rolls[0]}"
                else:
                    modifier_text = f"+{modifier}" if modifier > 0 else str(modifier)
                    result_text = f"Rolling 1d{sides}{modifier_text}: {rolls[0]} {modifier_text} = {final_total}"
            else:
                rolls_text = str(rolls).replace(" ", "")  # Remove spaces for cleaner display
                if modifier == 0:
                    result_text = f"Rolling {count}d{sides}: {rolls_text} = {total_before_modifier}"
                else:
                    modifier_text = f"+{modifier}" if modifier > 0 else str(modifier)
                    result_text = f"Rolling {count}d{sides}{modifier_text}: {rolls_text} {modifier_text} = {final_total}"
            
            logger.info(f"Dice roll executed: {result_text}")
            
            return {
                "success": True,
                "rolls": rolls,
                "total_before_modifier": total_before_modifier,
                "modifier": modifier,
                "final_total": final_total,
                "result_text": result_text,
                "dice_notation": f"{count}d{sides}" + (f"{'+' if modifier > 0 else ''}{modifier}" if modifier != 0 else "")
            }
            
        except Exception as e:
            logger.error(f"Error rolling dice: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Dice roll failed: {str(e)}"
            }
    
    def format_results_for_llm(self, result: Dict[str, Any]) -> str:
        """Format dice roll results for LLM consumption"""
        if not result.get("success"):
            return f"Dice roll failed: {result.get('error', 'Unknown error')}"
        
        return result.get("result_text", "Dice roll completed")