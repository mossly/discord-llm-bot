# Discord Bot powered by OpenAI GPT-4

This Discord bot is powered by OpenAI's API and allows users to interact with the bot through text-based conversations in a Discord server. 

## Features

- Connects to Discord using the Discord API
- Interacts with users through text-based conversations
- Utilizes OpenAI's GPT-4 API for generating responses
- Supports different response modes (verbose, concise, and creative)
- Supports referencing previous messages for better context

## Installation

1. Clone this repository:

    ```
    git clone <repository-url>
    ```

2. Change to the repository directory:

    ```
    cd <repository-directory>
    ```

3. Install the required dependencies:

    ```
    pip install -r requirements.txt
    ```

4. Create a `.env` file in the root directory and add the following environment variables:

    ```
    BOT_API_TOKEN=<your-discord-bot-api-token>
    OPENAI_API_KEY=<your-openai-api-key>
    SYSTEM_PROMPT=<your-system-prompt>
    BOT_TAG=<your-bot-tag>
    ```

5. Replace `<your-discord-bot-api-token>` with your Discord bot's API token, `<your-openai-api-key>` with your OpenAI API key, `<your-system-prompt>` with the desired system prompt for GPT-4, and `<your-bot-tag>` with the tag used to mention the bot in Discord (e.g., `@GPT4Bot`).

## Usage

1. Start the bot by running:

    ```
    python bot.py
    ```

2. The bot should now be connected to your Discord server.

3. To interact with the bot, simply mention it in a message, followed by your query:

    ```
    @GPT4Bot What is the capital of France?
    ```

4. To use different response modes, add the corresponding suffix to your message:

    - `-v`: Verbose mode
    - `-t`: Turbo mode
    - `-c`: Creative mode

    Example:

    ```
    @GPT4Bot Explain quantum mechanics -v
    ```

5. To reference a previous message, first reply to the message you want to reference, and then mention the bot with your query:

    ```
    @User1 What is the square root of 16?
    @User2 It's 4.
    @GPT4Bot Is that correct? (Replying to User2's message)
    ```

## Contributing

Contributions to this project are welcome! If you'd like to contribute, please follow these steps:

1. Fork the repository
2. Create a new branch with your changes
3. Commit your changes and push them to your fork
4. Create a pull request with a description of your changes

## License

This project is licensed under the MIT License. 
