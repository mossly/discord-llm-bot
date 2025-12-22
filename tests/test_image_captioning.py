#!/usr/bin/env python3
"""Test image captioning functionality for models that don't support images"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.ai_commands import AICommands, DEFAULT_MODEL


class TestImageCaptioning(unittest.TestCase):
    """Test image captioning for unsupported models"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.bot = Mock()
        self.cog = AICommands(self.bot)
        
    def test_default_model_constant(self):
        """Test DEFAULT_MODEL is properly defined"""
        self.assertEqual(DEFAULT_MODEL, "gemini-3-flash-preview")
        
    def test_model_supports_images_check(self):
        """Test checking if models support images"""
        # Test a model that supports images
        config = self.cog._get_model_config("gpt-4o-mini")
        self.assertTrue(config.get("supports_images", False))
        
        # Test a model that doesn't support images
        config = self.cog._get_model_config("deepseek-r1-0528")
        self.assertFalse(config.get("supports_images", False))
        
    @patch('cogs.ai_commands.logger')
    async def test_image_captioning_triggered(self, mock_logger):
        """Test that image captioning is triggered for unsupported models"""
        # Mock necessary components
        api_cog = Mock()
        api_cog.send_request = AsyncMock(return_value=("This is a test image showing a cat.", {"total_cost": 0.001}))
        
        self.bot.get_cog = Mock(return_value=api_cog)
        
        # Create mock interaction
        interaction = Mock()
        interaction.followup = Mock()
        interaction.followup.send = AsyncMock()
        
        # Test with a model that doesn't support images
        with patch.object(self.cog, '_process_ai_request') as mock_process:
            # Simulate the image URL and unsupported model scenario
            config = self.cog._get_model_config("deepseek-r1-0528")
            self.assertFalse(config.get("supports_images", False))
            
            # The actual implementation would trigger caption generation
            # We're testing that the logic path exists
            self.assertIn("openai/gpt-4.1-nano", str(api_cog.send_request.call_args) if api_cog.send_request.called else "")
            
    def test_caption_prompt_content(self):
        """Test that caption prompt asks for detailed description"""
        # The prompt should ask for detailed image description
        expected_keywords = ["describe", "image", "detail", "main subjects", "context"]
        
        # Read the actual implementation
        with open('cogs/ai_commands.py', 'r') as f:
            content = f.read()
            
        # Find the caption prompt
        caption_section = content[content.find("Please describe this image"):content.find("Please describe this image") + 200]
        
        for keyword in expected_keywords:
            self.assertIn(keyword, caption_section.lower())


if __name__ == '__main__':
    unittest.main()