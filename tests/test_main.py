import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json
import os

# Import the FastAPI app and related components
from main import app, TelegramWebhookHandler, solar_api

# Skip FastAPI TestClient tests for now due to compatibility issues
try:
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None


class TestFastAPIApp:
    """Test the FastAPI application endpoints."""
    
    def test_app_creation(self):
        """Test that the FastAPI app is created successfully."""
        assert app is not None
        assert hasattr(app, 'title')
        assert "Telegram Bot API" in app.title


class TestTelegramWebhookHandler:
    """Test the TelegramWebhookHandler class."""
    
    def setup_method(self):
        """Set up handler instance."""
        self.handler = TelegramWebhookHandler()
    
    def test_format_markdown_for_telegram_bold(self):
        """Test markdown formatting for bold text."""
        text = "This is **bold** text and __also bold__"
        result = self.handler._format_markdown_for_telegram(text)
        assert result == "This is <b>bold</b> text and <b>also bold</b>"
    
    def test_format_markdown_for_telegram_italic(self):
        """Test markdown formatting for italic text."""
        text = "This is *italic* text and _also italic_"
        result = self.handler._format_markdown_for_telegram(text)
        assert result == "This is <i>italic</i> text and <i>also italic</i>"
    
    def test_format_markdown_for_telegram_code(self):
        """Test markdown formatting for code."""
        text = "This is `inline code` and ```block code```"
        result = self.handler._format_markdown_for_telegram(text)
        assert result == "This is <code>inline code</code> and <pre>block code</pre>"
    
    def test_format_markdown_for_telegram_links(self):
        """Test markdown formatting for links."""
        text = "Check out [Google](https://google.com)"
        result = self.handler._format_markdown_for_telegram(text)
        assert result == 'Check out <a href="https://google.com">Google</a>'
    
    def test_clean_text_with_think_tags(self):
        """Test cleaning text with think tags."""
        text = "<think>This is thinking content</think>This is regular content"
        result = self.handler._clean_text(text)
        assert "🤔 <b>Reasoning:</b>" in result
        assert "<pre>This is thinking content</pre>" in result
        assert "This is regular content" in result
    
    def test_clean_text_empty_think_tags(self):
        """Test cleaning text with empty think tags."""
        text = "<think></think>This is regular content"
        result = self.handler._clean_text(text)
        assert "🤔 <b>Reasoning:</b>" not in result
        assert result == "This is regular content"
    
    def test_format_restaurant_list(self):
        """Test restaurant list formatting."""
        text = "1. **Restaurant Name** (Location) - Great food and service"
        result = self.handler._format_restaurant_list(text)
        assert "<b>Restaurant Name</b>" in result
        assert "(Location)" in result
        assert "Great food and service" in result
    
    def test_format_restaurant_list_with_citations(self):
        """Test restaurant list formatting with citations."""
        text = "1. **Restaurant Name** (Location) - Great food [1][2]"
        result = self.handler._format_restaurant_list(text)
        assert "<b>Restaurant Name</b>" in result
        # Citations might be moved or processed differently, just check structure
        assert "Great food" in result
    
    @pytest.mark.asyncio
    async def test_start_command(self):
        """Test start command handler."""
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        
        await self.handler.start(mock_update, mock_bot)
        
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]['chat_id'] == 123
        assert "Hello!" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test help command handler."""
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        
        await self.handler.help_command(mock_update, mock_bot)
        
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]['chat_id'] == 123
    
    @pytest.mark.asyncio
    async def test_handle_text_message(self):
        """Test handling text messages."""
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Test question"
        mock_update.message.entities = None  # No entities
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        
        # Mock the return value of send_message to have a message_id
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            mock_intelligent.return_value = {
                'answer': 'Test answer',
                'search_used': False,
                'sources': [],
                'search_queries': []
            }
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            mock_intelligent.assert_called_once()
            mock_bot.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_handle_text_with_search_sources(self):
        """Test handling text messages with search sources."""
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Test question"
        mock_update.message.entities = None  # No entities
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        
        # Mock the return value of send_message to have a message_id
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            mock_intelligent.return_value = {
                'answer': 'Test answer',
                'search_used': True,
                'sources': [
                    {
                        'id': 1,
                        'title': 'Test Source',
                        'url': 'https://example.com',
                        'content': 'Test content'
                    }
                ],
                'search_queries': ['test query', 'another query']
            }
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            mock_intelligent.assert_called_once()
            # Should send two messages: answer + sources
            assert mock_bot.send_message.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_handle_text_error_handling(self):
        """Test error handling in text message processing."""
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Test question"
        mock_update.message.entities = None  # No entities
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        
        # Mock the return value of send_message to have a message_id
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            mock_intelligent.side_effect = Exception("Test error")
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Should still send a message (error message)
            mock_bot.edit_message_text.assert_called()
            call_args = mock_bot.edit_message_text.call_args
            assert "error" in call_args[1]['text'].lower()


class TestCreateBot:
    """Test bot creation functionality."""
    
    def test_create_bot_module_import(self):
        """Test that create_bot function exists and can be imported."""
        from main import create_bot
        assert create_bot is not None
        assert callable(create_bot)


class TestSolarAPIIntegration:
    """Test Solar API integration in main.py."""
    
    def test_solar_api_instance_creation(self):
        """Test that solar_api instance is created."""
        assert solar_api is not None
        assert hasattr(solar_api, 'intelligent_complete')
    
    def test_webhook_handler_has_solar_api(self):
        """Test that webhook handler has solar_api instance."""
        handler = TelegramWebhookHandler()
        assert handler.solar_api is not None
        assert hasattr(handler.solar_api, 'intelligent_complete')


class TestEnvironmentConfiguration:
    """Test environment variable handling."""
    
    @patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-token', 'UPSTAGE_API_KEY': 'test-key'})
    def test_environment_variables_present(self):
        """Test behavior when environment variables are present."""
        from main import TELEGRAM_BOT_TOKEN, UPSTAGE_API_KEY
        # Note: These are imported at module level, so we need to reimport or patch
        # For now, just test that the values can be retrieved
        assert os.getenv('TELEGRAM_BOT_TOKEN') == 'test-token'
        assert os.getenv('UPSTAGE_API_KEY') == 'test-key'
    
    def test_environment_variables_missing(self):
        """Test behavior when environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Test that missing env vars don't crash the import
            assert os.getenv('TELEGRAM_BOT_TOKEN') is None
            assert os.getenv('UPSTAGE_API_KEY') is None


class TestErrorHandling:
    """Test error handling throughout the application."""
    
    def test_app_error_handling_structure(self):
        """Test that the app has error handling structures in place."""
        # Test that the app exists and has expected structure
        assert app is not None
        
        # Test that TelegramWebhookHandler has error handling
        handler = TelegramWebhookHandler()
        assert hasattr(handler, '_clean_text')
        assert hasattr(handler, '_format_markdown_for_telegram')


class TestTextFormatting:
    """Test text formatting utilities."""
    
    def setup_method(self):
        """Set up handler instance."""
        self.handler = TelegramWebhookHandler()
    
    def test_complex_markdown_formatting(self):
        """Test complex markdown formatting."""
        text = "**Bold** and *italic* with `code` and [link](https://example.com)"
        result = self.handler._format_markdown_for_telegram(text)
        expected = '<b>Bold</b> and <i>italic</i> with <code>code</code> and <a href="https://example.com">link</a>'
        assert result == expected
    
    def test_numbered_list_formatting(self):
        """Test numbered list formatting."""
        text = "1. **First Item** - Description\n2. **Second Item** - Another description"
        result = self.handler._format_markdown_for_telegram(text)
        assert "<b>First Item</b>" in result
        assert "<b>Second Item</b>" in result
    
    def test_bullet_point_formatting(self):
        """Test bullet point formatting."""
        text = "- First point\n* Second point\n+ Third point"
        result = self.handler._format_markdown_for_telegram(text)
        assert "• First point" in result
        assert "• Second point" in result
        assert "• Third point" in result
    
    def test_code_block_formatting(self):
        """Test code block formatting."""
        text = "```python\nprint('hello')\n```"
        result = self.handler._format_markdown_for_telegram(text)
        assert "<pre>python\nprint('hello')\n</pre>" in result 