# Discord Bot with Advanced AI Capabilities

This Discord bot leverages LLM models through OpenRouter and OpenAI APIs to provide AI chat, image generation, and web search capabilities directly in Discord.

## Features

- **Multiple AI Models**: Supports various models including GPT-4o-mini, o3-mini, Claude 3.7 Sonnet, Gemini 2.0 Flash Lite, Grok 2, Mistral Large, and more
- **Image Processing**: GPT-4o-mini can analyze and respond to images in conversations
- **Context-Aware Responses**: Maintains conversation context through message references
- **Image Generation**: Creates images using DALL-E 3 with customizable quality and orientation
- **Web Search Integration**: Performs DuckDuckGo searches to enhance responses with real-time information
- **Fun Mode**: Toggle between standard and more entertaining responses
- **Reminders**: Set, list, and cancel time-based reminders
- **Emoji Support**: Integrates with server emojis for more expressive responses
- **Discord Slash Commands**: Intuitive command interface with parameter descriptions
- **Context Menu Commands**: Right-click on messages to generate AI responses

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   - `BOT_API_TOKEN`: Your Discord bot token
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `OPENROUTER_API_KEY`: Your OpenRouter API key
   - `SYSTEM_PROMPT`: Default system prompt for AI responses
   - `FUN_PROMPT`: System prompt for fun mode responses
   - `BOT_TAG`: Your bot's mention tag
   - `DUCK_PROXY` (optional): Proxy for DuckDuckGo searches

4. Run the bot:
   ```
   python discordbot.py
   ```

## Commands

### Slash Commands

- `/chat`: Main command for AI interactions
  - `model`: Choose from multiple AI models
  - `prompt`: Your query or instructions
  - `fun`: Toggle fun response mode
  - `web_search`: Toggle web search integration
  - `attachment`: Optional image or text file

- `/gen`: Generate images with DALL-E 3
  - `prompt`: Description of the image to create
  - `hd`: Toggle HD quality
  - `orientation`: Choose image aspect ratio (Square, Landscape, Portrait)

### Context Menu Commands

- **AI Reply**: Right-click any message to generate an AI response
  - Provides a modal for additional context
  - Allows selecting model and toggles for fun mode and web search

## AI Model Options

The bot supports several AI models with different capabilities:

| Model | API | Features |
|-------|-----|----------|
| GPT-4o-mini | OpenRouter | Image support, general purpose |
| GPT-o3-mini | OpenRouter | Reasoning-focused |
| DeepSeek v3 | OpenRouter | Text-only chat |
| Claude 3.7 Sonnet | OpenRouter | Text-only chat |
| Claude 3.7 Sonnet (Thinking) | OpenRouter | Enhanced reasoning |
| Gemini 2.0 Flash Lite | OpenRouter | Text-only chat |
| Grok 2 | OpenRouter | Text-only chat |
| Mistral Large | OpenRouter | Text-only chat |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.