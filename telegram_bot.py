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
            "• /help - Show this help message\n\n"
            "🤖 <b>How it works:</b>\n"
            "I intelligently decide whether your question needs current web information or can be answered with general knowledge:\n\n"
            "🧠 <b>Direct Answer:</b> For general knowledge, programming, science concepts\n"
            "🌐 <b>Web Search:</b> For current events, real-time data, recent news\n\n"
            "💡 <b>Usage:</b>\n"
            "Simply ask any question! I'll automatically choose the best approach and provide sources when using web search.\n\n"
            "⚡️ Powered by <a href='https://console.upstage.ai'>Upstage SolarLLM</a>"
        )

        await update.message.reply_text(
            help_text, parse_mode="HTML", disable_web_page_preview=True
        )
    
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
        
        # Handle soft breaks (replace single newlines within paragraphs with space)
        # text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
        
        return text

    def _clean_text(self, text: str) -> str:
        """Clean text by formatting think tags and markdown into Telegram-compatible HTML."""
        def escape_html(text):
            """Escape HTML special characters."""
            html_escape_table = {
                "&": "&amp;",
                '"': "&quot;",
                "'": "&apos;",
                ">": "&gt;",
                "<": "&lt;",
            }
            return "".join(html_escape_table.get(c, c) for c in text)

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
        status_message = await update.message.reply_text(f"🤔 Analyzing: {user_question[:30]}...")

        try:
            # Variables to track the process
            accumulated_text = ""
            search_queries = []
            sources = []
            search_used = False
            
            # Throttling parameters for streaming
            last_update_time = time.time()
            last_update_length = 0
            min_update_interval = 0.5  # Min seconds between edits
            min_update_chars = 50      # Min new characters before attempting edit

            # Callback functions for the intelligent API
            def on_search_start():
                """Called when search is detected as needed"""
                nonlocal search_used
                search_used = True
                # This runs in a separate thread, so we need to use call_soon_threadsafe
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    status_message.edit_text(f"🔍 Searching for information about: {user_question[:30]}..."),
                    loop
                )

            def on_search_done(search_sources):
                """Called when search is completed with sources"""
                nonlocal sources
                sources = search_sources
                logger.info(f"Search completed with {len(sources)} sources")

            def on_update(content):
                """Called for each streaming update"""
                nonlocal accumulated_text, last_update_length, last_update_time
                accumulated_text += content
                
                current_time = time.time()
                current_length = len(accumulated_text)

                # Check throttling conditions
                if (current_length > last_update_length and
                    current_length - last_update_length >= min_update_chars and
                    current_time - last_update_time >= min_update_interval):
                    
                    try:
                        # Clean the text before sending to Telegram
                        cleaned_text = self._clean_text(accumulated_text)
                        # Use different prefixes based on whether search was used
                        prefix = "🌐 <b>Answer:</b>" if search_used else "🧠 <b>Answer:</b>"
                        
                        loop = asyncio.get_event_loop()
                        asyncio.run_coroutine_threadsafe(
                            status_message.edit_text(
                                f"{prefix} {cleaned_text}...",
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            ),
                            loop
                        )
                        last_update_length = current_length
                        last_update_time = current_time
                    except Exception as e:
                        logger.warning(f"Error updating streaming message: {e}")

            # Use the intelligent API in a separate thread
            result = await asyncio.to_thread(
                self.solar_api.intelligent_complete,
                user_query=user_question,
                model="solar-pro2-preview",
                stream=True,
                on_update=on_update,
                on_search_start=on_search_start,
                on_search_done=on_search_done
            )

            # Get the final result
            final_answer = result['answer']
            search_was_used = result['search_used']
            final_sources = result['sources']

            # Update the final message
            cleaned_text = self._clean_text(final_answer)
            prefix = "🌐 <b>Answer:</b>" if search_was_used else "🧠 <b>Answer:</b>"
            
            await status_message.edit_text(
                f"{prefix} {cleaned_text}",
                parse_mode="HTML",
                disable_web_page_preview=True
            )

            # If search was used, show sources
            if search_was_used and final_sources:
                logger.info(f"Sending sources: {len(final_sources)} found")
                
                # Create sources message
                sources_message = "<b>📚 Sources:</b>\n"
                source_links = []
                
                for i, source in enumerate(final_sources[:10], 1):  # Limit to 10 sources
                    title = source.get('title', 'Source')
                    url = source.get('url', '')
                    
                    # Extract domain for display
                    display_name = title
                    if url:
                        try:
                            domain = urlparse(url).netloc
                            if domain.startswith('www.'):
                                domain = domain[4:]
                            # Use domain if title is generic or missing
                            if not title or title.lower() in ["source", "untitled", "no title"]:
                                display_name = domain or "source"
                        except Exception:
                            pass
                    
                    # Ensure display name is not empty and escape HTML
                    display_name = display_name or "source"
                    display_name = display_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    
                    # Create link if URL is present
                    if url:
                        source_links.append(f"[{i}] <a href='{url}'>{display_name}</a>")
                    else:
                        source_links.append(f"[{i}] {display_name}")

                sources_message += "\n".join(source_links)

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