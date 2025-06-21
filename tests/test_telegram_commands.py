import pytest
from unittest.mock import Mock, AsyncMock, patch
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes

from telegram_bot import TelegramBot


class TestTelegramMemoryCommands:
    """Test the new memory-related telegram commands."""
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram update object."""
        update = Mock(spec=Update)
        update.message = Mock(spec=Message)
        update.message.reply_text = AsyncMock()
        update.effective_chat = Mock(spec=Chat)
        update.effective_chat.type = "private"
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram context object."""
        return Mock(spec=ContextTypes.DEFAULT_TYPE)
    
    @pytest.fixture
    def telegram_bot(self):
        """Create a TelegramBot instance with mocked SolarAPI."""
        with patch('telegram_bot.SolarAPI') as mock_solar:
            bot = TelegramBot("fake_token")
            return bot, mock_solar.return_value
    
    @pytest.mark.asyncio
    async def test_memory_command_with_memory_enabled(self, mock_update, mock_context, telegram_bot):
        """Test /memory command when memory is enabled."""
        bot, mock_solar_api = telegram_bot
        
        # Mock memory stats
        mock_solar_api.get_memory_stats.return_value = {
            "total_conversations": 5,
            "word_count": 1250,
            "has_summary": True,
            "last_updated": "2024-01-15 10:30:00",
            "memory_file_exists": True
        }
        
        # Execute the command
        await bot.memory_command(mock_update, mock_context)
        
        # Verify the response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        # Check that the response contains expected information
        assert "🧠 <b>Memory Status</b>" in response_text
        assert "💬 <b>Conversations:</b> 5" in response_text
        assert "📝 <b>Word Count:</b> 1,250" in response_text
        assert "📋 <b>Has Summary:</b> Yes" in response_text
        assert "🕒 <b>Last Updated:</b> 2024-01-15 10:30:00" in response_text
        assert "Use /clear to clear all memory" in response_text
        
        # Check that HTML parsing is enabled
        assert call_args[1]["parse_mode"] == "HTML"
    
    @pytest.mark.asyncio
    async def test_memory_command_with_memory_disabled(self, mock_update, mock_context, telegram_bot):
        """Test /memory command when memory is disabled."""
        bot, mock_solar_api = telegram_bot
        
        # Mock memory stats for disabled memory
        mock_solar_api.get_memory_stats.return_value = {
            "memory_disabled": True
        }
        
        # Execute the command
        await bot.memory_command(mock_update, mock_context)
        
        # Verify the response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        # Check that the response indicates memory is disabled
        assert "🧠 <b>Memory Status:</b> Disabled" in response_text
        assert "Memory functionality is currently disabled" in response_text
        assert call_args[1]["parse_mode"] == "HTML"
    
    @pytest.mark.asyncio
    async def test_memory_command_error_handling(self, mock_update, mock_context, telegram_bot):
        """Test /memory command error handling."""
        bot, mock_solar_api = telegram_bot
        
        # Mock an exception
        mock_solar_api.get_memory_stats.side_effect = Exception("Memory error")
        
        # Execute the command
        await bot.memory_command(mock_update, mock_context)
        
        # Verify error response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        assert "❌ Error retrieving memory status" in response_text
    
    @pytest.mark.asyncio
    async def test_clear_command_success(self, mock_update, mock_context, telegram_bot):
        """Test /clear command successful execution."""
        bot, mock_solar_api = telegram_bot
        
        # Execute the command
        await bot.clear_command(mock_update, mock_context)
        
        # Verify that clear_memory was called
        mock_solar_api.clear_memory.assert_called_once()
        
        # Verify the response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        # Check that the response indicates success
        assert "🧹 <b>Memory Cleared!</b>" in response_text
        assert "All conversation history and memory have been cleared" in response_text
        assert "Starting fresh! 🆕" in response_text
        assert call_args[1]["parse_mode"] == "HTML"
    
    @pytest.mark.asyncio
    async def test_clear_command_error_handling(self, mock_update, mock_context, telegram_bot):
        """Test /clear command error handling."""
        bot, mock_solar_api = telegram_bot
        
        # Mock an exception
        mock_solar_api.clear_memory.side_effect = Exception("Clear error")
        
        # Execute the command
        await bot.clear_command(mock_update, mock_context)
        
        # Verify error response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        assert "❌ Error clearing memory" in response_text
    
    @pytest.mark.asyncio
    async def test_help_command_includes_memory_commands(self, mock_update, mock_context, telegram_bot):
        """Test that /help command includes the new memory commands."""
        bot, mock_solar_api = telegram_bot
        
        # Execute the help command
        await bot.help_command(mock_update, mock_context)
        
        # Verify the response includes memory commands
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        # Check that memory commands are documented
        assert "• /memory - Show memory status" in response_text
        assert "• /clear - Clear all memory" in response_text
        assert "🧠 <b>Memory:</b> I remember our conversations" in response_text
    
    def test_command_handlers_registered(self, telegram_bot):
        """Test that the new command handler methods exist on the bot."""
        bot, mock_solar_api = telegram_bot
        
        # Verify that the command handler methods exist
        assert hasattr(bot, 'memory_command'), "memory_command method should exist"
        assert hasattr(bot, 'clear_command'), "clear_command method should exist"
        
        # Verify that the methods are callable
        assert callable(bot.memory_command), "memory_command should be callable"
        assert callable(bot.clear_command), "clear_command should be callable"
        
        # Verify existing command methods still exist
        assert hasattr(bot, 'start'), "start method should exist"
        assert hasattr(bot, 'help_command'), "help_command method should exist"


class TestMemoryCommandFormats:
    """Test formatting and edge cases for memory commands."""
    
    @pytest.fixture
    def telegram_bot(self):
        """Create a TelegramBot instance with mocked SolarAPI."""
        with patch('telegram_bot.SolarAPI') as mock_solar:
            bot = TelegramBot("fake_token")
            return bot, mock_solar.return_value
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram update object."""
        update = Mock(spec=Update)
        update.message = Mock(spec=Message)
        update.message.reply_text = AsyncMock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram context object."""
        return Mock(spec=ContextTypes.DEFAULT_TYPE)
    
    @pytest.mark.asyncio
    async def test_memory_command_number_formatting(self, mock_update, mock_context, telegram_bot):
        """Test that word count numbers are properly formatted with commas."""
        bot, mock_solar_api = telegram_bot
        
        # Mock memory stats with large numbers
        mock_solar_api.get_memory_stats.return_value = {
            "total_conversations": 1234,
            "word_count": 5678901,
            "has_summary": False,
            "last_updated": "Never",
            "memory_file_exists": True
        }
        
        # Execute the command
        await bot.memory_command(mock_update, mock_context)
        
        # Verify number formatting
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        assert "💬 <b>Conversations:</b> 1234" in response_text
        assert "📝 <b>Word Count:</b> 5,678,901" in response_text
        assert "📋 <b>Has Summary:</b> No" in response_text
        assert "🕒 <b>Last Updated:</b> Never" in response_text
    
    @pytest.mark.asyncio
    async def test_memory_command_empty_stats(self, mock_update, mock_context, telegram_bot):
        """Test memory command with empty/zero stats."""
        bot, mock_solar_api = telegram_bot
        
        # Mock empty memory stats
        mock_solar_api.get_memory_stats.return_value = {
            "total_conversations": 0,
            "word_count": 0,
            "has_summary": False,
            "last_updated": None,
            "memory_file_exists": False
        }
        
        # Execute the command
        await bot.memory_command(mock_update, mock_context)
        
        # Verify response handles empty stats gracefully
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        
        assert "💬 <b>Conversations:</b> 0" in response_text
        assert "📝 <b>Word Count:</b> 0" in response_text
        assert "📋 <b>Has Summary:</b> No" in response_text
        assert "🕒 <b>Last Updated:</b> None" in response_text 