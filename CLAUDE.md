# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Discord bot that integrates multiple LLM models through OpenRouter and OpenAI APIs. The bot provides AI chat, image generation, web search, task management, reminders, and advanced tool-calling functionalities directly in Discord servers.

## Architecture

### Core Components
- **Main Bot**: `discordbot.py` - Entry point that loads cogs and starts the bot
- **Conversation Handler**: `conversation_handler.py` - Manages threaded AI conversations
- **Configuration**: `config_manager.py` - Centralized environment variable management

### Cogs System
All bot functionality is organized in the `/cogs/` directory as Discord.py cogs:
- `ai_commands.py` - Main `/chat` slash command and AI interactions  
- `image_gen.py` - DALL-E 3 image generation (`/gen` command)
- `reminders.py` - Natural language reminder system with recurrence
- `tasks.py` - Task management with priority and status tracking
- `tool_calling.py` - Advanced LLM tool-calling framework
- `ddg_search.py` - DuckDuckGo web search integration
- `quota_management.py` - User quota management and admin commands
- `conversation_search.py` - Search conversation history
- `timezone_management.py` - User timezone handling
- `api_utils.py` - API communication utilities

### Tool System
Advanced tool-calling system in `/cogs/tools/`:
- `base_tool.py` - Base class for all tools
- `tool_registry.py` - Tool registration and management
- `web_search_tool.py` - Web search capabilities
- `reminder_tool.py` - Create and manage reminders
- `task_management_tool.py` - Task creation and updates
- `conversation_search_tool.py` - Search past conversations
- `discord_message_search_tool.py` - Real-time Discord search
- `discord_user_lookup_tool.py` - User information lookup
- `content_tool.py` - Content retrieval from URLs
- `recurrence_tools.py` - Reminder recurrence management

### Utilities
Helper modules in `/utils/`:
- `generic_chat.py` - Core chat processing logic
- `embed_utils.py` - Discord embed creation and splitting
- `attachment_handler.py` - File and image processing
- `response_formatter.py` - Format AI responses with footnotes
- `conversation_logger.py` - Log conversations to disk
- `quota_validator.py` - Check and track user quotas
- `time_parser.py` - Natural language time parsing
- `task_manager.py` - Task backend management
- `reminder_manager.py` - Reminder backend management

## Key Components

### Model Configuration
The bot supports multiple AI models with different capabilities configured in `ai_commands.py`:
- GPT-4o-mini (with image support)
- o4-mini (latest OpenAI model)
- Claude Sonnet 4
- DeepSeek R1
- Gemini 2.5 Flash
- Grok 3

**IMPORTANT**: Model configurations are hardcoded in `ai_commands.py` for performance reasons. Loading model configurations from external files would introduce unacceptable latency for Discord interactions. Any changes to model configurations must be made directly in the code and require a deployment.

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
- Automatic thread creation for AI conversations

## Development Commands

### Setup and Running
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python discordbot.py

# Run all tests
python tests/run_all_tests.py

# Run specific test suite (tool calling tests)
python tests/test_tool_calling.py
```

### Testing
The bot has comprehensive test coverage for the tool-calling system:
- `test_base_tool.py` - Base tool functionality tests
- `test_tool_registry.py` - Tool registration tests
- `test_web_search_tool.py` - Web search tool tests
- `test_content_tool.py` - Content retrieval tests
- `test_integration.py` - Full integration tests

### User Notification
When user input is required (e.g., waiting for approval, confirmation, or manual intervention), use the following command to notify the user with an audible beep:

```bash
echo -e "\a"
```

This is especially useful during long-running operations or when the assistant needs to pause for user input.

### Git Workflow
**IMPORTANT**: Always commit and push changes at the end of any implementation or significant code changes:

```bash
git add -A
git commit -m "Descriptive commit message"
git push
```

This ensures that all work is properly saved and synchronized with the remote repository.

### Environment Variables Required
- `BOT_API_TOKEN` - Discord bot token
- `OPENAI_API_KEY` - OpenAI API key
- `OPENROUTER_API_KEY` - OpenRouter API key
- `SYSTEM_PROMPT` - Default system prompt
- `FUN_PROMPT` - Fun mode system prompt
- `BOT_TAG` - Bot's mention tag
- `DUCK_PROXY` (optional) - Proxy for DuckDuckGo searches
- `BOT_ADMIN_IDS` (optional) - Comma-separated list of admin Discord user IDs
- `BOT_UNLIMITED_USER_IDS` (optional) - Comma-separated list of Discord user IDs with unlimited quota

### System Prompt Configuration
The bot's system prompt is configured through environment variables only:
- **`SYSTEM_PROMPT`**: Set the default system prompt for normal interactions
- **`FUN_PROMPT`**: Set the system prompt for fun mode interactions

**IMPORTANT**: System prompts should ONLY be loaded from environment variables. File-based loading has been removed for security and consistency.

**Datetime Context**: The bot automatically adds current date/time context to user messages (not system prompts) to provide temporal awareness to the AI.

**Footnote Format**: When the AI needs to include citations or references, it should use the following specific format to avoid conflicts with numbered lists:
- End the main content with exactly this separator: `---FOOTNOTES---`
- After the separator, list all footnotes/references
- This format prevents false positives where numbered lists get incorrectly moved to the footer

## Code Patterns

### Cog Structure
All functionality is implemented as Discord.py cogs that inherit from `commands.Cog`. Each cog handles specific feature areas and is loaded automatically by the main bot.

### Error Handling
API calls use tenacity for retry logic. Discord interactions include proper error responses and logging.

### Async Processing
Heavy operations like API calls and file processing use async/await patterns to avoid blocking the Discord event loop.

### Tool Development
When creating new tools:
1. Inherit from `BaseTool` in `/cogs/tools/base_tool.py`
2. Implement required methods: `get_schema()`, `run()`, `_validate_params()`
3. Register tool in `tool_calling.py` cog's `setup()` method
4. Tools should return structured data that can be formatted for Discord

## User Quota System

### Overview
The bot implements a monthly usage quota system to track and limit API costs per user. All users are assigned a default $1.00/month quota, with unlimited access configurable via environment variables.

### Quota Storage
- User quotas and usage are stored in `/data/user_quotas.json`
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

**CRITICAL REQUIREMENT**: All persistent data files MUST be stored in the `/data` directory or subdirectories within `/data`. This is a hard requirement for the Render hosting environment where the bot runs.

### Data Storage Rules
1. **Never use relative paths** like `./file.json` or `file.json` for persistent data
2. **Always use absolute paths** starting with `/data/` for all persistent storage
3. **Create subdirectories** within `/data/` to organize different types of data
4. **Ensure `/data` directory exists** before writing files (`os.makedirs("/data", exist_ok=True)`)

### Current Data Files
- User quotas (`/data/user_quotas.json`) ✅ Compliant
- Conversation history (`/data/conversation_history.json`) ✅ Compliant
- Reminders database (`/data/reminders.db`) ✅ Compliant
- Tasks database (`/data/tasks.db`) ✅ Compliant
- User timezones (`/data/user_timezones.db`) ✅ Compliant

### Container Storage Context
The `/data` directory requirement exists because:
- Docker containers use ephemeral filesystems by default
- Only the `/data` directory is mounted as a persistent volume
- Files outside `/data` are lost during container restarts/updates
- This ensures data continuity across Watchtower auto-updates

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

## Task Management System

The bot includes a comprehensive task management system:

### Features
- Natural language task creation through LLM tools
- Priority levels (low, medium, high)
- Status tracking (pending, in_progress, completed)
- User-specific task lists
- Integration with reminders for time-based tasks

### Commands
- `/task` - Interact with AI for task management using natural language
- Tasks are managed through the AI conversation flow

## Reminder System

### Features
- Natural language time parsing
- Recurrence support (daily, weekly, monthly, etc.)
- Timezone-aware scheduling
- SQLite backend for reliability
- Integration with task management

### Storage
- Uses SQLite database (`reminders.db`) for persistent storage
- Handles timezone conversions automatically
- Supports complex recurrence patterns

## Deployment

The Discord bot runs as a Docker container on TrueNAS Scale, with automatic updates via Watchtower.

### Docker Architecture
- **Image**: `ghcr.io/mossly/discord-llm-bot:latest`
- **Location**: `/mnt/Machina/apps/discord-llm-bot/`
- **Data Volume**: `./data:/data` - Persistent storage for databases and logs
- **Auto-updates**: Watchtower pulls new images from GHCR on each push to `main`

### GitHub Actions CI/CD
When code is pushed to `main`, GitHub Actions automatically:
1. Builds a new Docker image
2. Pushes to GitHub Container Registry (GHCR)
3. Watchtower on TrueNAS detects and pulls the new image

### Initial Deployment (TrueNAS)
```bash
# SSH into TrueNAS
ssh claude-truenas

# Create app directory
sudo mkdir -p /mnt/Machina/apps/discord-llm-bot
cd /mnt/Machina/apps/discord-llm-bot

# Copy docker-compose.yml and create .env
# (copy from repo or create manually)
sudo nano .env  # Add required environment variables

# Start the bot
sudo docker compose up -d

# View logs
sudo docker logs -f discord-llm-bot
```

### Environment Configuration
Create a `.env` file with required variables (see `.env.example` in repo):
```bash
BOT_API_TOKEN=your_discord_token
OPENAI_API_KEY=sk-your_openai_key
OPENROUTER_API_KEY=sk-or-your_openrouter_key
SYSTEM_PROMPT=Your system prompt here
FUN_PROMPT=Your fun mode prompt here
BOT_ADMIN_IDS=comma,separated,user,ids
BOT_UNLIMITED_USER_IDS=comma,separated,user,ids
```

### Common Operations
```bash
# View logs
ssh claude-truenas "sudo docker logs -f discord-llm-bot"
ssh claude-truenas "sudo docker logs --tail 100 discord-llm-bot"

# Restart bot
ssh claude-truenas "sudo docker restart discord-llm-bot"

# Force pull latest image
ssh claude-truenas "cd /mnt/Machina/apps/discord-llm-bot && sudo docker compose pull && sudo docker compose up -d"

# Check container status
ssh claude-truenas "sudo docker ps | grep discord-llm-bot"

# Access bot shell
ssh claude-truenas "sudo docker exec -it discord-llm-bot bash"

# View data files
ssh claude-truenas "sudo ls -la /mnt/Machina/apps/discord-llm-bot/data/"
```

### Data Persistence
Persistent data is stored in `/mnt/Machina/apps/discord-llm-bot/data/`:
- `user_quotas.json` - User quota tracking
- `conversation_history.json` - Logged conversations
- `reminders.db` - SQLite reminder database
- `tasks.db` - SQLite task database
- `user_timezones.db` - User timezone preferences