from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import logging
import asyncio
import json
import time
import re
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import httpx

from telegram import Update, Bot
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from solar import SolarAPI

# Load environment variables from .env.local file
load_dotenv('.env.local')

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Telegram Bot API",
    description="A Telegram bot powered by Solar API with grounding search",
    version="1.0.0"
)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")

if not UPSTAGE_API_KEY:
    logger.error("UPSTAGE_API_KEY environment variable not set!")

def create_bot():
    """Create a new bot instance optimized for serverless environments"""
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    try:
        # Configure HTTPXRequest with serverless-optimized settings
        request_instance = HTTPXRequest(
            connection_pool_size=1,   # Minimal pool size for serverless
            pool_timeout=10.0,        # Shorter timeouts
            connect_timeout=5.0,      
            read_timeout=15.0,        
            write_timeout=15.0       
        )
        
        # Create bot with optimized settings
        bot = Bot(token=TELEGRAM_BOT_TOKEN, request=request_instance)
        logger.info("Bot created with serverless-optimized settings")
        return bot
    except Exception as e:
        logger.error(f"Error creating bot with HTTPXRequest: {e}")
        # Fallback to default bot initialization
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            logger.info("Bot created with default settings")
            return bot
        except Exception as fallback_error:
            logger.error(f"Error creating bot with default settings: {fallback_error}")
            return None

solar_api = SolarAPI()

class TelegramWebhookHandler:
    def __init__(self):
        self.solar_api = SolarAPI()
    
    def _format_markdown_for_telegram(self, text: str) -> str:
        """Convert common Markdown syntax to Telegram-compatible HTML format."""
        # Handle bold text: **text** or __text__ -> <b>text</b>
        text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', lambda m: f'<b>{m.group(1) or m.group(2)}</b>', text)
        
        # Handle italic text: *text* or _text_ -> <i>text</i>
        text = re.sub(r'\*(.*?)\*|_(.*?)_(?![*_])', lambda m: f'<i>{m.group(1) or m.group(2)}</i>', text)
        
        # Handle code blocks: ```text``` -> <pre>text</pre>
        text = re.sub(r'```(.*?)```', lambda m: f'<pre>{m.group(1)}</pre>', text, flags=re.DOTALL)
        
        # Handle inline code: `text` -> <code>text</code>
        text = re.sub(r'`(.*?)`', lambda m: f'<code>{m.group(1)}</code>', text)
        
        # Handle links: [text](url) -> <a href="url">text</a>
        text = re.sub(r'\[(.*?)\]\((.*?)\)', lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
        
        # Process numbered lists with preservation of structure
        def process_numbered_list(match):
            number = match.group(1)
            content = match.group(2)
            return f"{number}. <b>{content}</b>\n"
            
        # Handle numbered lists with item title formatting (assumes format: "1. **Title** - content")
        text = re.sub(r'(\d+)\.\s+\*\*(.*?)\*\*\s+(.*?)(?=\n\d+\.|\n\n|$)', 
                      lambda m: f"{m.group(1)}. <b>{m.group(2)}</b>\n{m.group(3)}\n", 
                      text, flags=re.DOTALL)
        
        # Handle bullet points with proper formatting
        text = re.sub(r'^\s*[-*+]\s+(.*?)$', r'• \1', text, flags=re.MULTILINE)
        
        # Ensure proper paragraph breaks (double newlines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def _clean_text(self, text: str) -> str:
        """Clean text by formatting think tags and markdown into Telegram-compatible HTML."""
        def replace_think_section(match):
            think_content = match.group(1).strip()
            if not think_content:  # Skip empty thinking sections
                return ""
            # Format thinking content with markdown support
            think_content = self._format_markdown_for_telegram(think_content)
            # Format as a visually distinct section
            return (
                "\n\n🤔 <b>Reasoning:</b> (tap to copy)\n"
                f"<pre>{think_content}</pre>\n"
            )
            
        # Process structured restaurant lists before markdown formatting
        text = self._format_restaurant_list(text)

        # Handle think tags
        text = re.sub(r'<think>(.*?)</think>', replace_think_section, text, flags=re.DOTALL)
        
        # Then format remaining text with markdown
        text = self._format_markdown_for_telegram(text)
        
        # Clean up any remaining think tags
        text = text.replace('<think>', '').replace('</think>', '')
        
        return text.strip()

    def _format_restaurant_list(self, text: str) -> str:
        """Process restaurant or numbered list patterns with proper formatting."""
        # Pattern for numbered list items with titles and descriptions
        # Example: 1. **Restaurant Name** (Location) - Description
        pattern = r'(\d+)\.\s+\*\*(.*?)\*\*\s*(\(.*?\))?\s*(?:-|\n-)\s*(.*?)(?=\n\d+\.|\Z)'
        
        def format_restaurant_item(match):
            number = match.group(1)
            name = match.group(2)
            location = match.group(3) or ""
            description = match.group(4).strip()
            
            # Extract citation references like [1][2] and preserve them
            citation_refs = re.findall(r'\[\d+\]', description)
            if citation_refs:
                citation_str = " ".join(citation_refs)
                # Remove citations from main text to reposition them
                description = re.sub(r'\[\d+\]', '', description)
                # Clean up spacing after citation removal
                description = re.sub(r'\s+', ' ', description)
                description = description.strip()
                # Add citation refs at the end of title line
                location_with_citations = f"{location} {citation_str}".strip()
            else:
                location_with_citations = location
            
            # Format bullet points in description if they exist
            description = re.sub(r'^\s*-\s+', '\n• ', description, flags=re.MULTILINE)
            # Ensure description starts with newline for proper formatting
            if not description.startswith('\n') and description:
                description = '\n' + description
                
            # Format with line breaks for better readability
            formatted_item = f"{number}. <b>{name}</b> {location}\n{description}\n"
            return formatted_item
            
        # Apply pattern with flags to handle multiline entries
        text = re.sub(pattern, format_restaurant_item, text, flags=re.DOTALL)
        
        return text

    async def start(self, update: Update, bot: Bot):
        """Send a message when the command /start is issued."""
        await bot.send_message(
            chat_id=update.effective_chat.id,
            text="Hello! Send me any question and I'll search for an answer using Solar API."
        )
    
    async def help_command(self, update: Update, bot: Bot):
        """Send help message when the command /help is issued."""
        help_text = (
            "☀️ <b>Welcome to Solar Bot!</b>\n\n"
            "📚 <b>Basic Commands:</b>\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n\n"
            "💡 <b>How to use:</b>\n"
            "Simply type any question, and I'll use Solar API with grounding to find you an answer!\n\n"
            "⚡️ Powered by <a href='https://console.upstage.ai'>Upstage SolarLLM</a>"
        )

        await bot.send_message(
            chat_id=update.effective_chat.id,
            text=help_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    async def handle_text(self, update: Update, bot: Bot):
        """Process user's question using Solar API with grounding."""
        
        # Check if this is a group chat and if the bot is tagged
        is_group_chat = update.effective_chat.type in ["group", "supergroup"]
        is_bot_mentioned = False

        # Get the bot's username safely
        bot_username = None
        try:
            # Initialize bot if needed and get username
            await bot.initialize()
            bot_username = bot.username
        except Exception as e:
            logger.warning(f"Could not get bot username: {e}")
            bot_username = None
            
        logger.info(f"Bot username: {bot_username}")

        # Check for bot mentions
        if bot_username and bot_username.lower() in update.message.text.lower():
            is_bot_mentioned = True
        
        # For direct mentions using @ symbol
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == 'mention':
                    mention = update.message.text[entity.offset:entity.offset + entity.length]
                    if bot_username and mention.lower() == f"@{bot_username.lower()}":
                        is_bot_mentioned = True
                        break
        
        # Skip processing for group messages where the bot isn't mentioned
        if is_group_chat and not is_bot_mentioned:
            logger.info(f"Skipping message in group chat - bot not mentioned: {update.message.text[:50]}...")
            return
        
        # Process the message as normal
        user_question = update.message.text
        
        # Remove bot name/username from the question for cleaner processing
        if bot_username:
            user_question = re.sub(f'@?{re.escape(bot_username)}', '', user_question, flags=re.IGNORECASE)
        user_question = user_question.strip()
        
        # Send initial status message
        status_message = await bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🔍 Searching for {user_question[:30]}..."
        )

        try:
            # Get response from Solar API with grounding
            accumulated_text = ""
            sources = []
            
            def stream_callback(content: str):
                nonlocal accumulated_text
                if content:
                    accumulated_text += content

            def search_done_callback(search_sources: list):
                nonlocal sources
                sources.extend(search_sources)
                if sources:
                    logger.info(f"Found {len(sources)} sources")
                    for idx, source in enumerate(sources):
                        logger.info(f"Source {idx+1}: {source.get('title', 'N/A')}, {source.get('url', 'N/A')}")

            # Call Solar API (this is blocking, so we'll run it in a thread)
            result = await asyncio.to_thread(
                self.solar_api.complete,
                model="solar-pro2-preview",
                prompt=user_question,
                search_grounding=True,
                return_sources=True,
                stream=True,
                on_update=stream_callback,
                search_done_callback=search_done_callback
            )

            # Clean the text before sending to Telegram
            cleaned_text = self._clean_text(accumulated_text)
            
            # Update with final answer
            await bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text=f"⚡<b>Answer:</b>\n{cleaned_text}",
                parse_mode="HTML",
                disable_web_page_preview=True
            )

            # Process citations if sources are available
            if sources:
                try:
                    citation_result_json = await asyncio.to_thread(
                        self.solar_api.add_citations,
                        response_text=accumulated_text,
                        sources=sources
                    )

                    # Parse the citation result
                    try:
                        citation_data = json.loads(citation_result_json)
                        references = citation_data.get("references", [])

                        # If no references were found from parsing, use the source data directly
                        if not references and sources:
                            logger.info("No citations found in text, using direct sources instead")
                            references = []
                            for idx, source in enumerate(sources):
                                references.append({
                                    "number": idx + 1,
                                    "url": source.get("url", ""),
                                    "title": source.get("title", "")
                                })

                        # If there are references, send them as a separate message
                        if references:
                            citations_message = "<b>Sources:</b>"
                            source_links = []
                            references.sort(key=lambda r: int(r.get("number", 0)))

                            for ref in references:
                                ref_num = ref.get("number", "")
                                url = ref.get("url", "")
                                title = ref.get("title", "")

                                display_name = title if title else "Source"
                                if url:
                                    try:
                                        domain = urlparse(url).netloc
                                        if domain.startswith('www.'):
                                            domain = domain[4:]
                                        if not title or title.lower() in ["source", "untitled"]:
                                            display_name = domain or "source"
                                    except Exception:
                                        pass

                                # Basic HTML escaping
                                display_name = display_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

                                if url:
                                    source_links.append(f"[{ref_num}] <a href='{url}'>{display_name}</a>")
                                else:
                                    source_links.append(f"[{ref_num}] {display_name}")

                            citations_message += "\n" + "\n".join(source_links)

                            await bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=citations_message,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )

                    except (json.JSONDecodeError, Exception) as e:
                        logger.error(f"Error processing citation JSON: {e}")
                        # Fallback to display sources directly
                        if sources:
                            plain_message = "Sources:\n" + "\n".join([
                                f"[{idx+1}] {source.get('title', 'Source')}: {source.get('url', '')}" 
                                for idx, source in enumerate(sources)
                            ])
                            await bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=plain_message,
                                disable_web_page_preview=True
                            )

                except Exception as e:
                    logger.error(f"Error during citation processing: {e}")

        except Exception as e:
            logger.error(f"Error in handle_text: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_message.message_id,
                text=f"❌ Error generating answer: {str(e)}"
            )
        finally:
            # Clean up bot connection in serverless environment
            try:
                await bot.shutdown()
            except Exception as e:
                logger.debug(f"Error during bot cleanup: {e}")

# Initialize webhook handler
webhook_handler = TelegramWebhookHandler()

@app.get("/")
async def root():
    return {
        "message": "Telegram Bot API is running!",
        "endpoints": {
            "webhook": "POST /webhook - Telegram webhook endpoint",
            "health": "GET /health - Health check",
            "set_webhook": "POST /set_webhook - Set webhook URL"
        }
    }

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates via webhook"""
    bot = None
    try:
        # Create a fresh bot instance for this request
        bot = create_bot()
        if not bot:
            logger.error("Failed to create bot instance")
            return {"status": "error", "message": "Bot not configured"}
        
        # Get the JSON data from the request
        json_data = await request.json()
        logger.info(f"Received webhook data: {json_data}")
        
        # Create Update object from the JSON data
        update = Update.de_json(json_data, bot)
        
        if not update:
            logger.warning("Received invalid update data")
            return {"status": "error", "message": "Invalid update data"}
        
        # Handle different types of updates
        if update.message:
            if update.message.text:
                if update.message.text.startswith('/start'):
                    await webhook_handler.start(update, bot)
                elif update.message.text.startswith('/help'):
                    await webhook_handler.help_command(update, bot)
                else:
                    await webhook_handler.handle_text(update, bot)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        # Always clean up the bot instance
        if bot:
            try:
                await bot.shutdown()
            except Exception as e:
                logger.debug(f"Error during bot cleanup: {e}")

@app.post("/set_webhook")
@app.get("/set_webhook")
async def set_webhook(request: Request, webhook_url: Optional[str] = None):
    """Set the webhook URL for the Telegram bot"""
    bot = create_bot()
    if not bot:
        raise HTTPException(status_code=500, detail="Bot not configured")
    
    try:
        # Auto-detect webhook URL from the request if not provided
        if not webhook_url:
            # Extract base URL from the request
            base_url = f"{request.url.scheme}://{request.url.netloc}"
            webhook_url = f"{base_url}/webhook"
            logger.info(f"Auto-detected webhook URL: {webhook_url}")
        else:
            # Use provided URL and ensure it ends with /webhook
            if not webhook_url.endswith('/webhook'):
                webhook_url = f"{webhook_url}/webhook"
        
        # Initialize bot and set the webhook
        await bot.initialize()
        success = await bot.set_webhook(url=webhook_url)
        if success:
            logger.info(f"Webhook successfully set to: {webhook_url}")
            return {
                "status": "success", 
                "webhook_url": webhook_url,
                "message": "Webhook set successfully! Your bot is now ready to receive messages."
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to set webhook")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Error setting webhook: {str(e)}")
    finally:
        # Clean up bot instance
        if bot:
            try:
                await bot.shutdown()
            except Exception as e:
                logger.debug(f"Error during bot cleanup: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "telegram_token_configured": bool(TELEGRAM_BOT_TOKEN),
        "upstage_api_key_configured": bool(UPSTAGE_API_KEY),
        "webhook_url_env": "Auto-detect from request",
        "auto_detect_webhook": True,
        "service": "Telegram Bot API"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 