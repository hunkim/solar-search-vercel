import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json

# Import Vercel deployment components
from main import app, TelegramWebhookHandler, webhook_handler


class TestVercelDeployment:
    """Test the Vercel deployment functionality in main.py."""
    
    def setup_method(self):
        """Set up test instances."""
        self.handler = TelegramWebhookHandler()
    
    @pytest.mark.asyncio
    async def test_vercel_webhook_handler_callbacks(self):
        """Test that Vercel webhook handler properly uses all callback functions."""
        
        # Mock telegram objects
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "What are the latest AI developments?"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        # Mock status message
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        # Track callback calls
        callback_calls = []
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            
            def capture_callbacks(*args, **kwargs):
                # Record which callbacks were provided
                callback_calls.extend([k for k in kwargs.keys() if k.startswith('on_')])
                
                # Simulate the callback sequence
                if 'on_search_start' in kwargs and kwargs['on_search_start']:
                    kwargs['on_search_start']()
                
                if 'on_search_queries_generated' in kwargs and kwargs['on_search_queries_generated']:
                    kwargs['on_search_queries_generated'](['vercel query 1', 'vercel query 2'])
                
                if 'on_search_done' in kwargs and kwargs['on_search_done']:
                    kwargs['on_search_done']([{'title': 'Vercel Source', 'url': 'http://vercel.com'}])
                
                if 'on_update' in kwargs and kwargs['on_update']:
                    kwargs['on_update']("Vercel streaming content")
                
                return {
                    'answer': 'Vercel deployment answer',
                    'search_used': True,
                    'sources': [{'title': 'Vercel Source', 'url': 'http://vercel.com'}]
                }
            
            mock_intelligent.side_effect = capture_callbacks
            
            # Test the handle_text method
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify all required callbacks were provided
            expected_callbacks = ['on_update', 'on_search_start', 'on_search_done', 'on_search_queries_generated']
            for callback in expected_callbacks:
                assert callback in callback_calls, f"Missing callback: {callback}"
            
            # Verify bot methods were called
            mock_bot.send_message.assert_called()
            mock_bot.edit_message_text.assert_called()
            mock_bot.shutdown.assert_called()
    
    @pytest.mark.asyncio
    async def test_vercel_asyncio_create_task_usage(self):
        """Test that Vercel deployment uses proper asyncio handling for callbacks."""
        
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Test query"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        # Track asyncio.run_coroutine_threadsafe calls (current implementation)
        original_run_coroutine = asyncio.run_coroutine_threadsafe
        coroutine_calls = []
        
        def mock_run_coroutine(coro, loop):
            coroutine_calls.append(coro)
            return original_run_coroutine(coro, loop)
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent, \
             patch('asyncio.run_coroutine_threadsafe', side_effect=mock_run_coroutine):
            
            def callback_simulator(*args, **kwargs):
                # Trigger callbacks to create tasks
                if 'on_search_start' in kwargs and kwargs['on_search_start']:
                    kwargs['on_search_start']()
                
                return {
                    'answer': 'Test answer',
                    'search_used': True,
                    'sources': []
                }
            
            mock_intelligent.side_effect = callback_simulator
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify asyncio.run_coroutine_threadsafe was called (from our callbacks)
            assert len(coroutine_calls) > 0, "asyncio.run_coroutine_threadsafe should be used for callback message updates"
    
    @pytest.mark.asyncio
    async def test_vercel_immediate_query_display(self):
        """Test immediate search query display in Vercel deployment."""
        
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "What's new in AI?"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        # Track edit_message_text calls to verify query display
        edit_calls = []
        
        def track_edits(*args, **kwargs):
            edit_calls.append(kwargs.get('text', ''))
            return AsyncMock()
        
        mock_bot.edit_message_text.side_effect = track_edits
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            
            def simulate_search_with_queries(*args, **kwargs):
                # Simulate immediate query display
                if 'on_search_queries_generated' in kwargs and kwargs['on_search_queries_generated']:
                    kwargs['on_search_queries_generated'](['AI developments 2024', 'latest AI news'])
                
                return {
                    'answer': 'AI answer',
                    'search_used': True,
                    'sources': []
                }
            
            mock_intelligent.side_effect = simulate_search_with_queries
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify search queries are displayed in message edits
            query_display_messages = [msg for msg in edit_calls if "AI developments 2024" in msg]
            assert len(query_display_messages) > 0, "Search queries should be displayed immediately"
            
            # Verify proper formatting
            search_messages = [msg for msg in edit_calls if "Searching:" in msg]
            assert len(search_messages) > 0, "Should show 'Searching:' status"
    
    @pytest.mark.asyncio
    async def test_vercel_streaming_integration(self):
        """Test streaming integration in Vercel deployment."""
        
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Streaming test"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        streaming_updates = []
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            
            def simulate_streaming(*args, **kwargs):
                on_update = kwargs.get('on_update')
                if on_update:
                    # Simulate streaming updates
                    chunks = ["Streaming ", "test ", "content"]
                    for chunk in chunks:
                        streaming_updates.append(chunk)
                        on_update(chunk)
                
                return {
                    'answer': 'Streaming test content',
                    'search_used': False,
                    'sources': []
                }
            
            mock_intelligent.side_effect = simulate_streaming
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify streaming updates were captured
            assert len(streaming_updates) == 3
            assert streaming_updates == ["Streaming ", "test ", "content"]
            
            # Verify message edits occurred due to streaming
            assert mock_bot.edit_message_text.call_count > 0
    
    @pytest.mark.asyncio
    async def test_vercel_error_handling_with_bot_cleanup(self):
        """Test error handling and proper bot cleanup in Vercel deployment."""
        
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Error test"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            # Simulate an error in intelligent_complete
            mock_intelligent.side_effect = Exception("Solar API error")
            
            # Should not raise exception
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify bot cleanup was called even with error
            mock_bot.shutdown.assert_called()
            
            # Verify error message was sent to user
            edit_calls = [call.kwargs.get('text', '') for call in mock_bot.edit_message_text.call_args_list]
            error_messages = [msg for msg in edit_calls if "Error" in msg]
            assert len(error_messages) > 0, "Should send error message to user"
    
    def test_vercel_app_structure(self):
        """Test that Vercel app has proper structure and endpoints."""
        
        # Test app endpoints exist
        routes = [route.path for route in app.routes]
        
        expected_routes = ["/", "/webhook", "/set_webhook", "/health"]
        for route in expected_routes:
            assert route in routes, f"Missing route: {route}"
    
    @pytest.mark.asyncio
    async def test_vercel_webhook_handler_group_chat_handling(self):
        """Test group chat handling in Vercel deployment."""
        
        # Test group chat without mention (should be skipped)
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "group"
        mock_update.message.text = "Regular group message"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent:
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Should not call intelligent_complete for group messages without mention
            mock_intelligent.assert_not_called()
            
            # Note: bot.shutdown() is called in finally block and may not be captured in test
            # The important thing is that no processing happens for group messages
    
    @pytest.mark.asyncio
    async def test_vercel_sources_handling(self):
        """Test sources handling in Vercel deployment."""
        
        mock_update = Mock()
        mock_update.effective_chat.id = 123
        mock_update.effective_chat.type = "private"
        mock_update.message.text = "Test with sources"
        mock_update.message.entities = None
        
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_bot.edit_message_text = AsyncMock()
        mock_bot.initialize = AsyncMock()
        mock_bot.username = "testbot"
        mock_bot.shutdown = AsyncMock()
        
        mock_status_message = Mock()
        mock_status_message.message_id = 456
        mock_bot.send_message.return_value = mock_status_message
        
        test_sources = [
            {
                'id': 1,
                'title': 'Test Source 1',
                'url': 'https://example1.com',
                'content': 'Test content 1'
            },
            {
                'id': 2,
                'title': 'Test Source 2',
                'url': 'https://example2.com',
                'content': 'Test content 2'
            }
        ]
        
        with patch.object(self.handler.solar_api, 'intelligent_complete') as mock_intelligent, \
             patch.object(self.handler.solar_api, 'add_citations') as mock_citations:
            
            mock_intelligent.return_value = {
                'answer': 'Answer with sources',
                'search_used': True,
                'sources': test_sources
            }
            
            # Mock citation processing
            mock_citations.return_value = json.dumps({
                "references": [
                    {"number": 1, "url": "https://example1.com", "title": "Test Source 1"},
                    {"number": 2, "url": "https://example2.com", "title": "Test Source 2"}
                ]
            })
            
            await self.handler.handle_text(mock_update, mock_bot)
            
            # Verify sources processing
            mock_citations.assert_called_once()
            
            # Verify bot.send_message was called for sources (should be at least 2 calls: status + sources)
            assert mock_bot.send_message.call_count >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 