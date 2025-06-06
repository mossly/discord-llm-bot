# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Discord bot that integrates multiple LLM models through OpenRouter and OpenAI APIs. The bot provides AI chat, image generation, web search, and reminder functionalities directly in Discord servers.

## Architecture

- **Main Bot**: `discordbot.py` - Entry point that loads cogs and starts the bot
- **Cogs System**: All bot functionality is organized in the `/cogs/` directory as Discord.py cogs
  - `ai_commands.py` - Main slash commands and context menu commands for AI interactions
  - `image_gen.py` - DALL-E 3 image generation functionality
  - `reminders.py` - Time-based reminder system
  - `ddg_search.py` - DuckDuckGo web search integration
  - `api_utils.py` - API utilities for OpenRouter and OpenAI
  - `fun_prompt.py` - Fun mode prompt management
- **Utilities**: 
  - `generic_chat.py` - Core chat processing logic and attachment handling
  - `embed_utils.py` - Discord embed creation and splitting utilities

## Key Components

### Model Configuration
The bot supports multiple AI models with different capabilities configured in `ai_commands.py`. Models include GPT-4o-mini (with image support), o3-mini, Claude 3.7 Sonnet, DeepSeek v3, Gemini 2.0 Flash Lite, Grok 2, and Mistral Large.

### API Integration
- Uses OpenRouter for most models and OpenAI directly for some
- Implements retry logic with tenacity for API reliability
- Supports both text and image inputs where model capabilities allow

### Discord Features
- Slash commands with parameter validation
- Context menu commands (right-click message interactions)
- Message reference handling for conversation context
- Embed splitting for Discord's character limits
- Server emoji integration

## Development Commands

### Setup and Running
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python discordbot.py
```

### Environment Variables Required
- `BOT_API_TOKEN` - Discord bot token
- `OPENAI_API_KEY` - OpenAI API key
- `OPENROUTER_API_KEY` - OpenRouter API key
- `SYSTEM_PROMPT` - Default system prompt
- `FUN_PROMPT` - Fun mode system prompt
- `BOT_TAG` - Bot's mention tag
- `DUCK_PROXY` (optional) - Proxy for DuckDuckGo searches

## Code Patterns

### Cog Structure
All functionality is implemented as Discord.py cogs that inherit from `commands.Cog`. Each cog handles specific feature areas and is loaded automatically by the main bot.

### Error Handling
API calls use tenacity for retry logic. Discord interactions include proper error responses and logging.

### Async Processing
Heavy operations like API calls and file processing use async/await patterns to avoid blocking the Discord event loop.