import re
import asyncio
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class TelegramConfig:
    """Configuration constants for Telegram bot behavior"""
    
    # Streaming throttling parameters
    MIN_UPDATE_INTERVAL = 2.0  # Seconds between updates to avoid flood control
    MIN_UPDATE_CHARS = 100     # Minimum character change for updates
    
    # Message length limits
    STREAMING_CHAR_LIMIT = 3800  # For streaming updates
    FINAL_CHAR_LIMIT = 4000      # For final messages
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAYS = [5, 10, 15]  # Seconds to wait between retries
    
    # Brief answer prompt template
    BRIEF_ANSWER_PROMPT = """Please provide a brief, concise answer suitable for Telegram messaging. Keep it under 3000 characters if possible.

Today's date: {current_date}
Current year: {current_year}

User question: {user_question}

Instructions: Be direct, clear, and concise. Use bullet points or numbered lists when appropriate. Avoid overly long explanations. If the question relates to current events or time-sensitive information, consider the current date context provided above."""


class TelegramFormatter:
    """Utility class for formatting text for Telegram messages"""
    
    @staticmethod
    def format_markdown_for_telegram(text: str) -> str:
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

    @staticmethod
    def format_restaurant_list(text: str) -> str:
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

    @staticmethod
    def clean_text(text: str) -> str:
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
            think_content = TelegramFormatter.format_markdown_for_telegram(think_content)
            # Format as a visually distinct section
            return (
                "\n\n🤔 <b>Reasoning:</b> (tap to copy)\n"
                f"<pre>{think_content}</pre>\n"
            )
            
        # Process structured restaurant lists before markdown formatting
        text = TelegramFormatter.format_restaurant_list(text)

        # Handle think tags
        text = re.sub(r'<think>(.*?)</think>', replace_think_section, text, flags=re.DOTALL)
        
        # Then format remaining text with markdown
        text = TelegramFormatter.format_markdown_for_telegram(text)
        
        # Clean up any remaining think tags
        text = text.replace('<think>', '').replace('</think>', '')
        
        return text.strip()


class TelegramMessageHandler:
    """Utility class for handling Telegram message operations with retry logic"""
    
    @staticmethod
    def create_enhanced_query(user_question: str) -> str:
        """Create an enhanced query for brief Telegram responses"""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "December 13, 2024"
        current_year = datetime.now().year
        
        return TelegramConfig.BRIEF_ANSWER_PROMPT.format(
            user_question=user_question,
            current_date=current_date,
            current_year=current_year
        )
    
    @staticmethod
    def should_update_stream(current_length: int, last_update_length: int, 
                           current_time: float, last_update_time: float) -> bool:
        """Determine if streaming message should be updated based on throttling rules"""
        return (
            current_length > last_update_length and
            current_length - last_update_length >= TelegramConfig.MIN_UPDATE_CHARS and
            current_time - last_update_time >= TelegramConfig.MIN_UPDATE_INTERVAL
        )
    
    @staticmethod
    def truncate_for_streaming(text: str) -> str:
        """Truncate text for streaming updates"""
        if len(text) > TelegramConfig.STREAMING_CHAR_LIMIT:
            return text[:TelegramConfig.STREAMING_CHAR_LIMIT] + "..."
        return text
    
    @staticmethod
    def truncate_for_final(text: str) -> str:
        """Truncate text for final messages"""
        if len(text) > TelegramConfig.FINAL_CHAR_LIMIT:
            return text[:TelegramConfig.FINAL_CHAR_LIMIT] + "..."
        return text
    
    @staticmethod
    async def send_message_with_retry(send_func, *args, **kwargs):
        """Send message with retry logic for flood control"""
        for attempt in range(TelegramConfig.MAX_RETRIES):
            try:
                return await send_func(*args, **kwargs)
            except Exception as e:
                if "flood control" in str(e).lower() and attempt < TelegramConfig.MAX_RETRIES - 1:
                    # Wait before retry for flood control
                    wait_time = TelegramConfig.RETRY_DELAYS[attempt]
                    logger.warning(f"Flood control hit, waiting {wait_time}s before retry {attempt + 1}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to send message after {attempt + 1} attempts: {e}")
                    if attempt == TelegramConfig.MAX_RETRIES - 1:
                        raise e  # Re-raise the last exception
                    break
        return None


class TelegramSourceFormatter:
    """Utility class for formatting source citations for Telegram"""
    
    @staticmethod
    def format_sources_message(sources: list) -> str:
        """Format sources into a Telegram-compatible message"""
        sources_message = "<b>📚 Sources:</b>\n"
        source_links = []
        
        for i, source in enumerate(sources[:10], 1):  # Limit to 10 sources
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
        return sources_message
    
    @staticmethod
    def format_citations_message(references: list) -> str:
        """Format citation references into a Telegram-compatible message"""
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
        return citations_message 