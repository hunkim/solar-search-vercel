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
from telegram_utils import (
    TelegramConfig,
    TelegramFormatter,
    TelegramMessageHandler,
    TelegramSourceFormatter
)

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
    
    def _clean_text(self, text: str) -> str:
        """Clean text using shared Telegram formatter"""
        return TelegramFormatter.clean_text(text)

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
            text=f"🤔 Analyzing your question: <i>{user_question[:50]}{'...' if len(user_question) > 50 else ''}</i>",
            parse_mode="HTML"
        )

        try:
            # Use intelligent complete for better search decision making
            search_queries_used = []
            
            def stream_callback(content: str):
                # For streaming updates during response generation
                pass
            
            def search_done_callback(search_sources: list, queries: list = None):
                nonlocal search_queries_used
                if queries:
                    search_queries_used.extend(queries)
                    logger.info(f"Search queries used: {queries}")
                if search_sources:
                    logger.info(f"Found {len(search_sources)} sources")

            # Variables to track the process
            accumulated_text = ""
            search_queries = []
            sources = []
            search_used = False
            
            # Telegram-friendly throttling parameters to avoid flood control
            last_update_time = time.time()
            last_update_length = 0

            # Get the main event loop once for all callbacks (Vercel serverless fix)
            try:
                main_loop = asyncio.get_running_loop()
            except RuntimeError:
                # Fallback if no running loop
                main_loop = None

            # Callback functions for the intelligent API
            def on_search_start():
                """Called when search is detected as needed"""
                nonlocal search_used
                search_used = True
                # Update status message
                try:
                    if main_loop:
                        asyncio.run_coroutine_threadsafe(
                            bot.edit_message_text(
                                chat_id=update.effective_chat.id,
                                message_id=status_message.message_id,
                                text=f"🔍 Search needed. Generating queries..."
                            ),
                            main_loop
                        )
                except Exception as e:
                    logger.warning(f"Error updating search start message: {e}")

            def on_search_queries_generated(queries):
                """Called when search queries are generated - show immediately"""
                nonlocal search_queries
                search_queries = queries
                logger.info(f"Search queries generated: {queries}")
                # Show the search queries to the user immediately for best UX
                queries_text = ", ".join(queries[:3])  # Show up to 3 queries
                try:
                    if main_loop:
                        asyncio.run_coroutine_threadsafe(
                            bot.edit_message_text(
                                chat_id=update.effective_chat.id,
                                message_id=status_message.message_id,
                                text=f"🔍 <b>Searching:</b> {queries_text[:90]}...",
                                parse_mode="HTML"
                            ),
                            main_loop
                        )
                except Exception as e:
                    logger.warning(f"Error updating search queries message: {e}")

            def on_search_done(search_sources):
                """Called when search is completed with sources"""
                nonlocal sources
                sources = search_sources
                logger.info(f"Search completed with {len(sources)} sources")
                # Update status to show search completion and start generating
                try:
                    if main_loop:
                        asyncio.run_coroutine_threadsafe(
                            bot.edit_message_text(
                                chat_id=update.effective_chat.id,
                                message_id=status_message.message_id,
                                text=f"✅ Found {len(sources)} sources. Generating answer..."
                            ),
                            main_loop
                        )
                except Exception as e:
                    logger.warning(f"Error updating search done message: {e}")

            def on_update(content):
                """Called for each streaming update"""
                nonlocal accumulated_text, last_update_length, last_update_time
                accumulated_text += content
                
                current_time = time.time()
                current_length = len(accumulated_text)

                # Conservative throttling to avoid flood control
                should_update = TelegramMessageHandler.should_update_stream(
                    current_length, last_update_length, current_time, last_update_time
                )

                if should_update:
                    try:
                        # Clean the text before sending to Telegram
                        cleaned_text = self._clean_text(accumulated_text)
                        # Use different prefixes based on whether search was used
                        prefix = "🌐 <b>Answer:</b>" if search_used else "🧠 <b>Answer:</b>"
                        
                        # Truncate if too long to avoid Telegram API limits during streaming
                        display_text = TelegramMessageHandler.truncate_for_streaming(cleaned_text)
                        
                        if main_loop:
                            asyncio.run_coroutine_threadsafe(
                                bot.edit_message_text(
                                    chat_id=update.effective_chat.id,
                                    message_id=status_message.message_id,
                                    text=f"{prefix} {display_text}",
                                    parse_mode="HTML",
                                    disable_web_page_preview=True
                                ),
                                main_loop
                            )
                        last_update_length = current_length
                        last_update_time = current_time
                    except Exception as e:
                        logger.warning(f"Error updating streaming message: {e}")

            # Enhance query for Telegram - request brief, concise answers
            enhanced_query = TelegramMessageHandler.create_enhanced_query(user_question)

            # Call Solar API with all callbacks
            result = await asyncio.to_thread(
                self.solar_api.intelligent_complete,
                user_query=enhanced_query,
                model=os.getenv("UPSTAGE_MODEL_NAME", "solar-pro2"),
                stream=True,
                on_update=on_update,
                on_search_start=on_search_start,
                on_search_done=on_search_done,
                on_search_queries_generated=on_search_queries_generated
            )
            
            # Get the final result
            final_answer = result['answer']
            search_was_used = result['search_used']
            final_sources = result['sources']

            # Always update with the final complete message to ensure nothing is truncated
            cleaned_text = self._clean_text(final_answer)
            prefix = "🌐 <b>Answer:</b>" if search_was_used else "🧠 <b>Answer:</b>"
            
            # Truncate for final message
            cleaned_text = TelegramMessageHandler.truncate_for_final(cleaned_text)
            
            # Send final message with retry logic
            async def send_final_message():
                return await bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_message.message_id,
                    text=f"{prefix} {cleaned_text}",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            
            try:
                await TelegramMessageHandler.send_message_with_retry(send_final_message)
            except Exception as e:
                # Last resort: try sending as new message
                try:
                    await bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"{prefix} {cleaned_text}",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as final_e:
                    logger.error(f"Failed to send final message as new message: {final_e}")

            # If search was used, show sources
            if search_was_used and final_sources:
                try:
                    citation_result_json = await asyncio.to_thread(
                        self.solar_api.add_citations,
                        response_text=final_answer,
                        sources=final_sources
                    )

                    # Parse the citation result
                    try:
                        citation_data = json.loads(citation_result_json)
                        references = citation_data.get("references", [])

                        # If no references were found from parsing, use the source data directly
                        if not references and final_sources:
                            logger.info("No citations found in text, using direct sources instead")
                            references = []
                            for idx, source in enumerate(final_sources):
                                references.append({
                                    "number": idx + 1,
                                    "url": source.get("url", ""),
                                    "title": source.get("title", "")
                                })

                        # If there are references, send them as a separate message
                        if references:
                            citations_message = TelegramSourceFormatter.format_citations_message(references)

                            await bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=citations_message,
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )

                    except (json.JSONDecodeError, Exception) as e:
                        logger.error(f"Error processing citation JSON: {e}")
                        # Fallback to display sources directly
                        if final_sources:
                            plain_message = "Sources:\n" + "\n".join([
                                f"[{idx+1}] {source.get('title', 'Source')}: {source.get('url', '')}" 
                                for idx, source in enumerate(final_sources)
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