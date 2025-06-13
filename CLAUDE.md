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
  - `quota_management.py` - User quota management and admin commands
- **Utilities**: 
  - `generic_chat.py` - Core chat processing logic and attachment handling
  - `embed_utils.py` - Discord embed creation and splitting utilities
  - `user_quotas.py` - User quota tracking and cost management system

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
- `SYSTEM_PROMPT` - Default system prompt (also see `.system_prompt.txt`)
- `FUN_PROMPT` - Fun mode system prompt
- `BOT_TAG` - Bot's mention tag
- `DUCK_PROXY` (optional) - Proxy for DuckDuckGo searches
- `BOT_ADMIN_IDS` (optional) - Comma-separated list of admin Discord user IDs
- `BOT_UNLIMITED_USER_IDS` (optional) - Comma-separated list of Discord user IDs with unlimited quota

### System Prompt Configuration
The bot's system prompt can be configured in two ways:
1. **Environment Variable**: Set `SYSTEM_PROMPT` environment variable
2. **File-based**: Edit `.system_prompt.txt` file which contains the detailed system prompt including tool descriptions and usage guidelines

The `.system_prompt.txt` file is the recommended approach as it provides better readability and version control for the comprehensive system prompt that includes detailed tool descriptions and agentic behavior guidelines.

## Code Patterns

### Cog Structure
All functionality is implemented as Discord.py cogs that inherit from `commands.Cog`. Each cog handles specific feature areas and is loaded automatically by the main bot.

### Error Handling
API calls use tenacity for retry logic. Discord interactions include proper error responses and logging.

### Async Processing
Heavy operations like API calls and file processing use async/await patterns to avoid blocking the Discord event loop.

## User Quota System

### Overview
The bot implements a monthly usage quota system to track and limit API costs per user. All users are assigned a default $1.00/month quota, with unlimited access configurable via environment variables.

### Quota Storage
- User quotas and usage are stored in `user_quotas.json`
- Data persists across bot restarts and updates
- Monthly tracking using `YYYY-MM` format keys

### Monthly Reset Behavior
- **Automatic**: No scheduled tasks required
- **Persistent**: Works across service interruptions, restarts, and updates
- **Lazy Evaluation**: Resets happen when users interact in a new month
- **Reliable**: Uses current date comparison, not timers

### Admin Management
Admins can manage quotas using the `/set-quota`, `/reset-usage`, `/quota-stats`, and `/user-quota` commands.

**Admin Authorization Methods:**
1. **Environment Variable**: Set `BOT_ADMIN_IDS` with comma-separated Discord user IDs
2. **File-based**: Create `admin_ids.txt` with one Discord user ID per line (supports `#` comments)

**Unlimited Quota Users:**
- Set `BOT_UNLIMITED_USER_IDS` environment variable with comma-separated Discord user IDs
- These users have unlimited API usage with no monthly restrictions

### Quota Commands
- `/quota` - Users check their own usage and remaining quota
- `/set-quota <user> <amount>` - [ADMIN] Set user's monthly quota
- `/reset-usage <user>` - [ADMIN] Reset user's current month usage
- `/quota-stats` - [ADMIN] View top users and overall statistics
- `/user-quota <user>` - [ADMIN] Detailed quota information for specific user

### Cost Tracking
- **Pre-call Validation**: Checks quota before API calls
- **Post-call Tracking**: Deducts actual costs from quotas
- **Real-time Updates**: Immediate quota adjustments
- **Comprehensive Coverage**: Text generation, image generation, and editing

## Data Persistence

**IMPORTANT**: All persistent data files must be stored in the `/data` directory or subdirectories within `/data`. This includes:

- User quotas (`/data/user_quotas.json`)
- Conversation history (`/data/conversation_history.json`)
- Reminders (`reminders.json` - should be moved to `/data/reminders.json`)
- User timezones (`user_timezones.json` - should be moved to `/data/user_timezones.json`)
- Any new persistent storage files

This ensures proper data organization and facilitates backup/deployment strategies.

## Conversation History System

The bot automatically logs all conversations between users and AI models for LLM tool access:

### Storage
- **File**: `/data/conversation_history.json`
- **Structure**: User-indexed JSON with conversation metadata
- **Capacity**: Auto-managed with size limits (100k conversations)

### LLM Tool Integration
- **Tool Name**: `search_conversations`
- **Purpose**: Allows LLMs to search previous conversations for context
- **Parameters**: query (required), user_id (required), limit (optional)
- **Use Cases**: Follow-up questions, context retrieval, conversation continuity

### User Commands
- `/stats` - View personal conversation statistics (total conversations, tokens, cost)

## Discord Message Search System

The bot provides real-time search capabilities through existing Discord message history:

### LLM Tool Integration
- **Tool Name**: `search_discord_messages`
- **Purpose**: Search through Discord server message history in real-time without prior logging
- **Parameters**: 
  - `query` (required): Search term or phrase
  - `channel_id` (optional): Specific channel to search
  - `server_id` (optional): Specific server to search
  - `limit` (optional): Max messages to search (default: 1000, max: 10000)
  - `author_id` (optional): Search messages from specific user
  - `time_range` (optional): Time range filter ('1h', '6h', '1d', '7d', '30d')
  - `case_sensitive` (optional): Case-sensitive search (default: false)
  - `exclude_bots` (optional): Exclude bot messages (default: true)
  - `max_results` (optional): Max results to return (default: 20, max: 50)

### Features
- **Real-time Search**: Accesses current Discord message history via API
- **Performance Optimized**: Rate limiting, chunked processing, result limits
- **Flexible Filtering**: Time ranges, users, channels, case sensitivity
- **Rich Results**: Message content, author info, timestamps, jump URLs
- **Permission Aware**: Only searches accessible channels

### Use Cases
- Finding past discussions or decisions
- Locating specific messages or announcements  
- Gathering context from previous conversations
- Research and reference lookup in server history

## Deployment

The Discord bot runs on a remote **Render** cloud instance. To manage the deployed bot, use the Render CLI from your local machine:

### Render CLI Commands
- `render login` - Authorize the CLI for your account
- `render services` - List all services (select the Discord bot service)
- `render deploys list [SERVICE_ID]` - View deployment history and logs
- `render deploys create [SERVICE_ID]` - Trigger a new deployment
- `render ssh [SERVICE_ID]` - Open SSH session to the running instance
- `render logs -r [SERVICE_ID] -o text --limit 100` - View recent logs (working command format)

### Common Operations
```bash
# View logs for debugging
render services -o json  # Get service ID (srv-cgdpib7ekgjpv7sspsf0)
render logs -r srv-cgdpib7ekgjpv7sspsf0 -o text --limit 100  # View recent logs
render logs -r srv-cgdpib7ekgjpv7sspsf0 -o text --limit 100 | grep "permission\|error"  # Search logs

# Deploy updates
render deploys create srv-cgdpib7ekgjpv7sspsf0 --wait

# SSH into the running instance
render ssh srv-cgdpib7ekgjpv7sspsf0
```

The bot's persistent data (quotas, conversation history, etc.) is stored in the `/data` directory on the Render instance.