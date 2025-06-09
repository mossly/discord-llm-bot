"""
Base tool interface for all tools in the system
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for all tools"""
    
    def __init__(self):
        self._usage_count = 0
        self._error_count = 0
        self._session_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0
        }
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON schema for tool parameters"""
        pass
    
    @property
    def usage_count(self) -> int:
        """Number of times this tool has been used"""
        return self._usage_count
    
    @property
    def error_count(self) -> int:
        """Number of errors encountered"""
        return self._error_count
    
    @property
    def session_stats(self) -> Dict[str, Any]:
        """Get current session usage statistics"""
        return self._session_stats.copy()
    
    def reset_session_stats(self):
        """Reset session statistics"""
        self._session_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0
        }
    
    def add_session_usage(self, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0.0):
        """Add usage to session statistics"""
        self._session_stats["input_tokens"] += input_tokens
        self._session_stats["output_tokens"] += output_tokens
        self._session_stats["cost"] += cost
    
    async def __call__(self, **kwargs) -> Dict[str, Any]:
        """Call the tool with error handling and logging"""
        try:
            logger.info(f"Executing tool '{self.name}' with parameters: {kwargs}")
            self._usage_count += 1
            result = await self.execute(**kwargs)
            logger.info(f"Tool '{self.name}' executed successfully")
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error executing tool '{self.name}': {e}", exc_info=True)
            return {
                "error": str(e),
                "tool": self.name,
                "success": False
            }
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters"""
        pass
    
    def get_openai_schema(self) -> Dict[str, Any]:
        """Get the tool schema in OpenAI format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def validate_parameters(self, **kwargs) -> Optional[str]:
        """Validate parameters against schema. Returns error message if invalid."""
        required = self.parameters.get("required", [])
        properties = self.parameters.get("properties", {})
        
        # Check required parameters
        for param in required:
            if param not in kwargs:
                return f"Missing required parameter: {param}"
        
        # Check parameter types (basic validation)
        for param, value in kwargs.items():
            if param in properties:
                expected_type = properties[param].get("type")
                if expected_type:
                    if expected_type == "string" and not isinstance(value, str):
                        return f"Parameter '{param}' must be a string"
                    elif expected_type == "integer" and not isinstance(value, int):
                        return f"Parameter '{param}' must be an integer"
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        return f"Parameter '{param}' must be a boolean"
                    elif expected_type == "array" and not isinstance(value, list):
                        return f"Parameter '{param}' must be an array"
                    elif expected_type == "object" and not isinstance(value, dict):
                        return f"Parameter '{param}' must be an object"
        
        return None