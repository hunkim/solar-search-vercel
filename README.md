# Telegram Bot with Solar API

A Telegram bot powered by Solar Pro Preview LLM from Upstage with web search grounding capabilities.

## Features

- 🤖 Telegram bot with webhook support (Vercel-ready)
- 🔍 Web search grounding using Tavily API
- ☀️ Solar Pro Preview LLM for intelligent responses
- 📚 Automatic citation and source formatting
- 👥 Group chat support with @mention detection
- 🎨 Rich text formatting with HTML support
- ⚡ Real-time streaming responses

## Setup

### 1. Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env.local` file in the project root:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Upstage API Configuration  
UPSTAGE_API_KEY=your_upstage_api_key_here

# Tavily Search API (for grounding)
TAVILY_API_KEY=your_tavily_api_key_here
```

> **That's it!** The webhook URL is automatically detected from your deployment.

### 3. Getting API Keys

**Telegram Bot Token:**
1. Chat with [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot using `/newbot`
3. Copy the bot token

**Upstage API Key:**
1. Sign up at [Upstage Console](https://console.upstage.ai)
2. Navigate to API Keys section
3. Create a new API key

**Tavily API Key:**
1. Sign up at [Tavily](https://tavily.com)
2. Get your API key from the dashboard

### Advanced Configuration (Optional)

**Custom Webhook URL Override:**
If you need to use a custom domain instead of your deployment URL, you can set:
```bash
WEBHOOK_URL=https://your-custom-domain.com
```

This is only needed for advanced use cases like custom domains or proxy setups.

### 4. Deploy to Vercel

```bash
# Deploy to Vercel
vercel --prod

# Set environment variables in Vercel dashboard
# Go to your project settings and add the environment variables
```

### 5. Set Webhook

After deployment, simply visit your webhook setup URL - **no configuration needed**!

```bash
# Just visit this URL in your browser or use curl
https://your-vercel-app.vercel.app/set_webhook
```

**That's it!** Your bot is now ready to receive messages.

## Local Development

### Run the FastAPI Server

```bash
# Development mode with auto-reload
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

### Testing Locally with ngrok

For local development, you can use ngrok to expose your local server:

```bash
# Install ngrok and expose port 8000
ngrok http 8000

# Visit the ngrok URL + /set_webhook 
# Example: https://abc123.ngrok.io/set_webhook
```

## Bot Features

### Commands

- `/start` - Welcome message and bot introduction
- `/help` - Display help information and available commands

### Text Processing

The bot processes any text message and:
1. Uses Tavily API to search for relevant information
2. Sends the search results to Solar Pro Preview LLM
3. Generates a comprehensive response with citations
4. Formats the response with proper HTML markup
5. Sends citations as a separate message with clickable links

### Group Chat Support

- Bot responds only when mentioned with `@botname`
- Automatically detects group chats vs private chats
- Strips bot mentions from questions for cleaner processing

## API Endpoints

### `GET /`
Welcome message with available endpoints.

### `POST /webhook`
Telegram webhook endpoint for receiving updates.

### `POST /set_webhook`
Set the webhook URL for the Telegram bot. **Auto-detects your deployment URL** if no custom URL provided.

**Simple Usage (auto-detection):**
```bash
curl -X POST "https://your-domain.com/set_webhook"
```

**Advanced Usage (custom URL):**
```json
{
  "webhook_url": "https://your-custom-domain.com"
}
```

**Response:**
```json
{
  "status": "success",
  "webhook_url": "https://your-domain.com/webhook",
  "message": "Webhook set successfully! Your bot is now ready to receive messages."
}
```

### `GET /health`
Health check endpoint showing configuration status.

**Response:**
```json
{
  "status": "healthy",
  "telegram_token_configured": true,
  "upstage_api_key_configured": true,
  "webhook_url": "https://your-domain.com",
  "service": "Telegram Bot API"
}
```

## Usage Examples

### Chat with the Bot

1. Start a chat with your bot on Telegram
2. Send `/start` to begin
3. Ask any question: "What's the weather in Seoul?"
4. The bot will search the web and provide an answer with sources

### Group Chat Usage

1. Add the bot to a group
2. Mention the bot: "@yourbotname What's the latest news about AI?"
3. The bot will respond with search results and citations

## Text Formatting Features

The bot supports rich text formatting:

- **Bold text** with `**text**`
- *Italic text* with `*text*`
- `Code snippets` with backticks
- ```Code blocks``` with triple backticks
- [Links](url) with markdown syntax
- Numbered and bulleted lists
- Automatic citation formatting

## Architecture

- **FastAPI**: Web framework for webhook handling
- **python-telegram-bot**: Telegram Bot API wrapper
- **Solar API**: LLM for generating responses
- **Tavily API**: Web search for grounding
- **Vercel**: Serverless deployment platform

## Troubleshooting

### Webhook Issues

Check webhook status:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

Delete webhook:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
```

### Environment Variables

Verify all required environment variables are set:
```bash
curl "https://your-vercel-app.vercel.app/health"
```

### Bot Not Responding

1. Check the webhook is set correctly
2. Verify environment variables in Vercel
3. Check the logs in Vercel dashboard
4. Ensure the bot token is valid

## Development

### File Structure

- `main.py` - FastAPI application with Telegram webhook handling
- `solar.py` - Solar API client with search grounding
- `telegram_bot.py` - Original polling-based bot (reference)
- `requirements.txt` - Python dependencies
- `vercel.json` - Vercel deployment configuration

### Running Tests

```bash
# Test the API endpoints
curl "http://localhost:8000/health"

# Test webhook handling (with mock data)
curl -X POST "http://localhost:8000/webhook" \
     -H "Content-Type: application/json" \
     -d '{"update_id": 1, "message": {"message_id": 1, "chat": {"id": 123}, "text": "/start"}}'
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
