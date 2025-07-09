import os
import logging
import asyncio
import json
from asyncio import Queue
import time
import re
from urllib.parse import urlparse
from dotenv import load_dotenv

from telegram import Update
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

# Load environment variables from .env.local
load_dotenv('.env.local')

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        #self.solar_api = SolarAPI()
        self.solar_api = SolarAPI()

        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("memory", self.memory_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        
        # Text handler
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        await update.message.reply_text(
            "🤖 Hello! I'm your Intelligent Solar Bot!\n\n"
            "Ask me anything and I'll automatically decide whether to:\n"
            "🧠 Answer directly from knowledge\n"
            "🌐 Search the web for current information\n\n"
            "Try me with questions like:\n"
            "• What is machine learning?\n"
            "• Latest AI developments in 2024\n"
            "• How to implement binary search?\n"
            "• Current weather in Seoul"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message when the command /help is issued."""
        help_text = (
            "☀️ <b>Welcome to Intelligent Solar Bot!</b>\n\n"
            "📚 <b>Basic Commands:</b>\n"
            "• /start - Start the bot\n"
            "• /help - Show this help message\n"
            "• /memory - Show memory status\n"
            "• /clear - Clear all memory\n\n"
            "🤖 <b>How it works:</b>\n"
            "I intelligently decide whether your question needs current web information or can be answered with general knowledge:\n\n"
            "🧠 <b>Direct Answer:</b> For general knowledge, programming, science concepts\n"
            "🌐 <b>Web Search:</b> For current events, real-time data, recent news\n\n"
            "💡 <b>Usage:</b>\n"
            "Simply ask any question! I'll automatically choose the best approach and provide sources when using web search.\n\n"
            "🧠 <b>Memory:</b> I remember our conversations to provide better context in future interactions.\n\n"
            "⚡️ Powered by <a href='https://console.upstage.ai'>Upstage SolarLLM</a>"
        )

        await update.message.reply_text(
            help_text, parse_mode="HTML", disable_web_page_preview=True
        )
    
    async def memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show quick memory status when the command /memory is issued."""
        try:
            # Get memory statistics from the Solar API
            memory_stats = self.solar_api.get_memory_stats()
            
            if memory_stats.get("memory_disabled", False):
                await update.message.reply_text(
                    "🧠 <b>Memory Status:</b> Disabled\n\n"
                    "Memory functionality is currently disabled.",
                    parse_mode="HTML"
                )
                return
            
            # Format memory statistics
            total_conversations = memory_stats.get("total_conversations", 0)
            word_count = memory_stats.get("word_count", 0)
            has_summary = memory_stats.get("has_summary", False)
            last_updated = memory_stats.get("last_updated", "Never")
            
            # Create status message
            status_text = (
                f"🧠 <b>Memory Status</b>\n\n"
                f"💬 <b>Conversations:</b> {total_conversations}\n"
                f"📝 <b>Word Count:</b> {word_count:,}\n"
                f"📋 <b>Has Summary:</b> {'Yes' if has_summary else 'No'}\n"
                f"🕒 <b>Last Updated:</b> {last_updated}\n\n"
                f"Use /clear to clear all memory"
            )
            
            await update.message.reply_text(status_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error getting memory status: {e}")
            await update.message.reply_text(
                "❌ Error retrieving memory status. Please try again later."
            )
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear all memory when the command /clear is issued."""
        try:
            # Clear memory using the Solar API
            self.solar_api.clear_memory()
            
            await update.message.reply_text(
                "🧹 <b>Memory Cleared!</b>\n\n"
                "All conversation history and memory have been cleared.\n"
                "Starting fresh! 🆕",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Error clearing memory: {e}")
            await update.message.reply_text(
                "❌ Error clearing memory. Please try again later."
            )

    def _clean_text(self, text: str) -> str:
        """Clean text using shared Telegram formatter"""
        return TelegramFormatter.clean_text(text)



    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process user's question using the new intelligent Solar API."""
        
        # Check if this is a group chat and if the bot is tagged
        is_group_chat = update.effective_chat.type in ["group", "supergroup"]
        is_bot_mentioned = False

        # Get the bot's username from context
        bot_username = context.bot.username if context.bot else None
        logger.info(f"Bot username: {bot_username}")

        # Optionally, store it for future reference
        if bot_username and not hasattr(self, 'bot_username'):
            self.bot_username = bot_username
            logger.info(f"Bot username detected: @{bot_username}")

        # Also check for existing bot name in message
        if bot_username and bot_username.lower() in update.message.text.lower():
            is_bot_mentioned = True
        
        # For direct mentions using @ symbol
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == 'mention':
                    mention = update.message.text[entity.offset:entity.offset + entity.length]
                    if mention.lower() == f"@{bot_username.lower()}":
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
        
        # Start with initial status message
        status_message = await update.message.reply_text(f"🤔 Analyzing: {user_question[:50]}...")

        try:
            # Variables to track the process
            accumulated_text = ""
            search_queries = []
            sources = []
            search_used = False
            
            # Telegram-friendly throttling parameters to avoid flood control
            last_update_time = time.time()
            last_update_length = 0

            # Get the main event loop once for all callbacks
            main_loop = asyncio.get_running_loop()

            # Callback functions for the intelligent API
            def on_search_start():
                """Called when search is detected as needed"""
                nonlocal search_used
                search_used = True
                # This runs in a separate thread, so we need to use call_soon_threadsafe
                try:
                    asyncio.run_coroutine_threadsafe(
                        status_message.edit_text(f"🔍 Search needed. Generating queries..."),
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
                    asyncio.run_coroutine_threadsafe(
                        status_message.edit_text(f"🔍 <b>Searching:</b> {queries_text[:90]}..."),
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
                    asyncio.run_coroutine_threadsafe(
                        status_message.edit_text(f"✅ Found {len(sources)} sources. Generating answer..."),
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

                # Log streaming activity for debugging
                logger.debug(f"Streaming update: +{len(content)} chars, total: {current_length}")

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
                        
                        logger.debug(f"Updating Telegram message, length: {len(display_text)}")
                        
                        asyncio.run_coroutine_threadsafe(
                            status_message.edit_text(
                                f"{prefix} {display_text}",
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            ),
                            main_loop
                        )
                        last_update_length = current_length
                        last_update_time = current_time
                        logger.debug("Telegram message updated successfully")
                    except Exception as e:
                        logger.warning(f"Error updating streaming message: {e}")

            # Enhance query for Telegram - request brief, concise answers
            enhanced_query = TelegramMessageHandler.create_enhanced_query(user_question)

            # Use the intelligent API with all callbacks including search queries
            logger.info(f"Starting intelligent_complete for: {user_question[:50]}...")
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
            logger.info(f"Intelligent_complete finished. Search used: {result.get('search_used', False)}")

            # Get the final result
            final_answer = result['answer']
            search_was_used = result['search_used']
            final_sources = result['sources']

            # Update the final message with retry logic for flood control
            cleaned_text = self._clean_text(final_answer)
            prefix = "🌐 <b>Answer:</b>" if search_was_used else "🧠 <b>Answer:</b>"
            
            # Truncate for final message
            cleaned_text = TelegramMessageHandler.truncate_for_final(cleaned_text)
            
            # Send final message with retry logic
            async def send_final_message():
                return await status_message.edit_text(
                    f"{prefix} {cleaned_text}",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            
            try:
                await TelegramMessageHandler.send_message_with_retry(send_final_message)
            except Exception as e:
                # Last resort: try sending as new message
                try:
                    await update.message.reply_text(
                        f"{prefix} {cleaned_text}",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as final_e:
                    logger.error(f"Failed to send final message as new message: {final_e}")

            # If search was used, show sources
            if search_was_used and final_sources:
                logger.info(f"Sending sources: {len(final_sources)} found")
                
                # Create sources message using shared formatter
                sources_message = TelegramSourceFormatter.format_sources_message(final_sources)

                try:
                    # Send sources as a separate message
                    await update.message.reply_text(
                        sources_message,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    logger.info("Successfully sent sources message.")
                except Exception as send_error:
                    logger.error(f"Error sending sources message: {send_error}")
                    # Try without HTML parsing as a fallback
                    try:
                        plain_message = "📚 Sources:\n" + "\n".join([
                            f"[{i}] {source.get('title', 'Source')}: {source.get('url', '')}" 
                            for i, source in enumerate(final_sources[:10], 1)
                        ])
                        await update.message.reply_text(
                            plain_message,
                            disable_web_page_preview=True
                        )
                        logger.info("Sent plaintext sources as fallback.")
                    except Exception as plain_error:
                        logger.error(f"Failed to send plaintext sources: {plain_error}")

        except Exception as e:
            logger.error(f"Error in handle_text: {e}", exc_info=True)
            try:
                await status_message.edit_text(f"❌ An error occurred: {str(e)}")
            except Exception as inner_e:
                logger.error(f"Failed to send error message to user: {inner_e}")


    def run(self):
        """Start the bot."""
        self.application.run_polling()


def main():
    """Initialize and start the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    bot = TelegramBot(token)
    logger.info("Starting bot...")
    bot.run()


if __name__ == "__main__":
    main() 