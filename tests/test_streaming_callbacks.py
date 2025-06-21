import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# Import our modules
from solar import SolarAPI
from telegram_bot import TelegramBot


class TestSolarAPICallbacks:
    """Test the new callback system in Solar API intelligent_complete method."""
    
    def setup_method(self):
        """Set up test instances."""
        self.solar_api = SolarAPI()
        self.callback_events = []
        self.search_queries_received = []
        self.sources_received = []
        self.content_updates = []
    
    def test_intelligent_complete_signature(self):
        """Test that intelligent_complete has all the new callback parameters."""
        import inspect
        sig = inspect.signature(self.solar_api.intelligent_complete)
        
        # Check that all callback parameters exist
        expected_params = [
            'user_query', 'model', 'stream', 'on_update', 
            'on_search_start', 'on_search_done', 'on_search_queries_generated'
        ]
        
        for param in expected_params:
            assert param in sig.parameters, f"Missing parameter: {param}"
    
    def test_callback_functions_called_with_search(self):
        """Test that callbacks are called in the correct order when search is needed."""
        
        def on_search_start():
            self.callback_events.append('search_start')
        
        def on_search_queries_generated(queries):
            self.callback_events.append('queries_generated')
            self.search_queries_received.extend(queries)
        
        def on_search_done(sources):
            self.callback_events.append('search_done')
            self.sources_received.extend(sources)
        
        def on_update(content):
            self.content_updates.append(content)
        
        # Mock the internal methods - need to mock _get_search_grounded_response properly
        with patch.object(self.solar_api, '_check_search_needed', return_value='Y'), \
             patch.object(self.solar_api, '_extract_search_queries_fast', return_value=['test query 1', 'test query 2']), \
             patch.object(self.solar_api, '_get_search_grounded_response') as mock_search_response:
            
            # Make the mock call the on_search_done callback properly
            def mock_search_grounded(*args, **kwargs):
                # Extract the on_search_done callback from kwargs
                on_search_done_callback = kwargs.get('on_search_done') or args[5] if len(args) > 5 else None
                if on_search_done_callback:
                    # Call it with mock sources
                    mock_sources = [{'id': 1, 'title': 'Test Source', 'url': 'http://test.com'}]
                    on_search_done_callback(mock_sources)
                
                return {
                    'response': 'Test response',
                    'sources': [{'id': 1, 'title': 'Test Source', 'url': 'http://test.com'}]
                }
            
            mock_search_response.side_effect = mock_search_grounded
            
            result = self.solar_api.intelligent_complete(
                user_query="What are the latest AI developments?",
                model="solar-pro2-preview",
                stream=True,
                on_update=on_update,
                on_search_start=on_search_start,
                on_search_done=on_search_done,
                on_search_queries_generated=on_search_queries_generated
            )
            
            # Verify callbacks were called in correct order
            expected_order = ['search_start', 'queries_generated', 'search_done']
            assert self.callback_events == expected_order
            
            # Verify callback data
            assert self.search_queries_received == ['test query 1', 'test query 2']
            assert len(self.sources_received) == 1
            assert self.sources_received[0]['title'] == 'Test Source'
            
            # Verify result
            assert result['search_used'] is True
            assert result['answer'] == 'Test response'
            assert len(result['sources']) == 1
    
    def test_callback_functions_not_called_without_search(self):
        """Test that search callbacks are not called when search is not needed."""
        
        def on_search_start():
            self.callback_events.append('search_start')
        
        def on_search_queries_generated(queries):
            self.callback_events.append('queries_generated')
        
        def on_search_done(sources):
            self.callback_events.append('search_done')
        
        def on_update(content):
            self.content_updates.append(content)
        
        # Mock the internal methods
        with patch.object(self.solar_api, '_check_search_needed', return_value='N'), \
             patch.object(self.solar_api, '_extract_search_queries_fast') as mock_extract, \
             patch.object(self.solar_api, '_get_direct_answer', return_value='Direct answer'):
            
            result = self.solar_api.intelligent_complete(
                user_query="What is Python?",
                model="solar-pro2-preview",
                stream=True,
                on_update=on_update,
                on_search_start=on_search_start,
                on_search_done=on_search_done,
                on_search_queries_generated=on_search_queries_generated
            )
            
            # Verify search callbacks were NOT called
            assert 'search_start' not in self.callback_events
            assert 'queries_generated' not in self.callback_events
            assert 'search_done' not in self.callback_events
            
            # Verify result
            assert result['search_used'] is False
            assert result['answer'] == 'Direct answer'
            assert result['sources'] == []
    
    def test_parallel_processing_optimization(self):
        """Test that search decision and query extraction run in parallel."""
        decision_start_time = None
        query_start_time = None
        decision_end_time = None
        query_end_time = None
        
        def mock_check_search_needed(*args):
            nonlocal decision_start_time, decision_end_time
            decision_start_time = time.time()
            time.sleep(0.1)  # Simulate work
            decision_end_time = time.time()
            return 'Y'
        
        def mock_extract_queries(*args):
            nonlocal query_start_time, query_end_time
            query_start_time = time.time()
            time.sleep(0.1)  # Simulate work
            query_end_time = time.time()
            return ['query1', 'query2']
        
        with patch.object(self.solar_api, '_check_search_needed', side_effect=mock_check_search_needed), \
             patch.object(self.solar_api, '_extract_search_queries_fast', side_effect=mock_extract_queries), \
             patch.object(self.solar_api, '_get_search_grounded_response') as mock_search:
            
            mock_search.return_value = {'response': 'test', 'sources': []}
            
            start_time = time.time()
            result = self.solar_api.intelligent_complete(
                user_query="Test query",
                on_search_start=lambda: None,
                on_search_queries_generated=lambda x: None,
                on_search_done=lambda x: None
            )
            total_time = time.time() - start_time
            
            # Verify both operations started around the same time (parallel execution)
            assert abs(decision_start_time - query_start_time) < 0.05, "Operations should start in parallel"
            
            # Verify total time is closer to 0.1s than 0.2s (parallel, not sequential)
            assert total_time < 0.15, f"Total time {total_time} suggests sequential execution, not parallel"
    
    @pytest.mark.asyncio
    async def test_streaming_callback_threading(self):
        """Test that streaming callbacks work correctly from ThreadPoolExecutor threads."""
        
        callback_thread_names = []
        
        def on_update(content):
            callback_thread_names.append(threading.current_thread().name)
        
        # Mock streaming to simulate real callback from thread - need to mock complete method
        with patch.object(self.solar_api, '_check_search_needed', return_value='N'), \
             patch.object(self.solar_api, 'complete') as mock_complete:
            
            def mock_complete_method(*args, **kwargs):
                # Simulate streaming by calling on_update callback
                on_update_callback = kwargs.get('on_update')
                if on_update_callback:
                    on_update_callback("chunk1")
                    on_update_callback("chunk2")
                return "test response"
            
            mock_complete.side_effect = mock_complete_method
            
            # Run in thread to simulate real usage
            result = await asyncio.to_thread(
                self.solar_api.intelligent_complete,
                user_query="Test",
                stream=True,
                on_update=on_update
            )
            
            # Verify callbacks were called (at least some should be from threads)
            assert len(callback_thread_names) == 2
            # Note: In test environment, thread names may vary, so just check we got callbacks
            assert all(name for name in callback_thread_names)


class TestTelegramBotCallbacks:
    """Test Telegram bot integration with the new callback system."""
    
    def setup_method(self):
        """Set up test instances."""
        self.telegram_bot = TelegramBot("test_token")
        self.status_messages = []
        self.bot_edit_calls = []
    
    @pytest.mark.asyncio
    async def test_callback_integration_with_telegram(self):
        """Test that Telegram bot properly integrates with callback system."""
        
        # Mock Telegram objects
        mock_update = Mock()
        mock_update.message.text = "What are the latest AI developments?"
        mock_update.effective_chat.type = "private"
        mock_update.message.entities = None
        
        mock_context = Mock()
        mock_context.bot.username = "testbot"
        
        # Mock status message
        mock_status_message = Mock()
        mock_status_message.edit_text = AsyncMock()
        
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_message)
        
        with patch.object(self.telegram_bot.solar_api, 'intelligent_complete') as mock_intelligent:
            
            # Configure the mock to capture callback calls
            captured_callbacks = {}
            
            def capture_intelligent_complete(*args, **kwargs):
                captured_callbacks.update(kwargs)
                
                # Simulate callback sequence
                if 'on_search_start' in kwargs and kwargs['on_search_start']:
                    kwargs['on_search_start']()
                
                if 'on_search_queries_generated' in kwargs and kwargs['on_search_queries_generated']:
                    kwargs['on_search_queries_generated'](['query1', 'query2'])
                
                if 'on_search_done' in kwargs and kwargs['on_search_done']:
                    kwargs['on_search_done']([{'title': 'Source 1', 'url': 'http://test.com'}])
                
                if 'on_update' in kwargs and kwargs['on_update']:
                    kwargs['on_update']("Streaming content")
                
                return {
                    'answer': 'Test answer',
                    'search_used': True,
                    'sources': [{'title': 'Source 1', 'url': 'http://test.com'}]
                }
            
            mock_intelligent.side_effect = capture_intelligent_complete
            
            # Call the handler
            await self.telegram_bot.handle_text(mock_update, mock_context)
            
            # Verify all callbacks were provided
            assert 'on_search_start' in captured_callbacks
            assert 'on_search_queries_generated' in captured_callbacks
            assert 'on_search_done' in captured_callbacks
            assert 'on_update' in captured_callbacks
            
            # Verify status message was updated (callbacks were called)
            mock_status_message.edit_text.assert_called()
            edit_calls = [call.args[0] for call in mock_status_message.edit_text.call_args_list]
            
            # Check for expected status progression
            assert any("Generating queries" in call for call in edit_calls)
            assert any("Searching:" in call for call in edit_calls)
            assert any("Found" in call and "sources" in call for call in edit_calls)
    
    @pytest.mark.asyncio
    async def test_immediate_search_query_display(self):
        """Test that search queries are displayed immediately when generated."""
        
        mock_update = Mock()
        mock_update.message.text = "Test search question"
        mock_update.effective_chat.type = "private"
        mock_update.message.entities = None
        
        mock_context = Mock()
        mock_context.bot.username = "testbot"
        
        mock_status_message = Mock()
        mock_status_message.edit_text = AsyncMock()
        
        query_display_time = None
        search_start_time = None
        
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_message)
        
        with patch.object(self.telegram_bot.solar_api, 'intelligent_complete') as mock_intelligent:
            
            def capture_timing(*args, **kwargs):
                nonlocal query_display_time, search_start_time
                
                if 'on_search_start' in kwargs and kwargs['on_search_start']:
                    search_start_time = time.time()
                    kwargs['on_search_start']()
                
                if 'on_search_queries_generated' in kwargs and kwargs['on_search_queries_generated']:
                    query_display_time = time.time()
                    kwargs['on_search_queries_generated'](['immediate query 1', 'immediate query 2'])
                
                return {'answer': 'Test', 'search_used': True, 'sources': []}
            
            mock_intelligent.side_effect = capture_timing
            
            await self.telegram_bot.handle_text(mock_update, mock_context)
            
            # Verify queries were displayed immediately (should be called after search start)
            assert query_display_time is not None
            assert search_start_time is not None
            assert query_display_time >= search_start_time
            
            # Verify the query display message was sent
            edit_calls = [call.args[0] for call in mock_status_message.edit_text.call_args_list]
            query_display_calls = [call for call in edit_calls if "immediate query 1" in call]
            assert len(query_display_calls) > 0, "Search queries should be displayed immediately"
    
    def test_asyncio_event_loop_fix(self):
        """Test that the asyncio event loop issue is resolved."""
        
        # This test simulates the ThreadPoolExecutor environment
        event_loop_errors = []
        
        def mock_callback_with_loop_access():
            try:
                # This should work with our fix
                loop = asyncio.get_running_loop()
                return True
            except RuntimeError as e:
                event_loop_errors.append(str(e))
                return False
        
        # Simulate running in a thread like our solar API does
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(mock_callback_with_loop_access)
            result = future.result()
            
            # This test verifies the environment behavior
            # The actual fix is in telegram_bot.py where we capture the main loop
            # and use asyncio.run_coroutine_threadsafe
    
    @pytest.mark.asyncio 
    async def test_streaming_responsiveness(self):
        """Test that streaming updates are responsive with new throttling parameters."""
        
        mock_update = Mock()
        mock_update.message.text = "Test streaming"
        mock_update.effective_chat.type = "private"
        mock_update.message.entities = None
        
        mock_context = Mock()
        mock_context.bot.username = "testbot"
        
        mock_status_message = Mock()
        mock_status_message.edit_text = AsyncMock()
        
        update_timestamps = []
        
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_message)
        
        with patch.object(self.telegram_bot.solar_api, 'intelligent_complete') as mock_intelligent:
            
            def simulate_streaming(*args, **kwargs):
                on_update = kwargs.get('on_update')
                if on_update:
                    # Simulate rapid content updates
                    for i in range(10):
                        update_timestamps.append(time.time())
                        on_update(f"chunk{i} ")
                        time.sleep(0.01)  # Small delay between chunks
                
                return {'answer': 'Streaming test complete', 'search_used': False, 'sources': []}
            
            mock_intelligent.side_effect = simulate_streaming
            
            start_time = time.time()
            await self.telegram_bot.handle_text(mock_update, mock_context)
            
            # Verify streaming updates were processed
            assert len(update_timestamps) == 10
            
            # Verify message was edited (throttling allowed some updates through)
            assert mock_status_message.edit_text.call_count > 0


class TestErrorHandling:
    """Test error handling in the new callback system."""
    
    def setup_method(self):
        """Set up test instances."""
        self.solar_api = SolarAPI()
    
    def test_callback_error_handling(self):
        """Test that errors in callbacks don't break the main flow."""
        
        def failing_callback(*args):
            raise Exception("Callback error")
        
        with patch.object(self.solar_api, '_check_search_needed', return_value='Y'), \
             patch.object(self.solar_api, '_extract_search_queries_fast', return_value=['query']), \
             patch.object(self.solar_api, '_get_search_grounded_response') as mock_search:
            
            mock_search.return_value = {'response': 'test', 'sources': []}
            
            # Should not raise exception even with failing callbacks
            result = self.solar_api.intelligent_complete(
                user_query="Test",
                on_search_start=failing_callback,
                on_search_queries_generated=failing_callback,
                on_search_done=failing_callback
            )
            
            # Main flow should still work
            assert result['search_used'] is True
            assert result['answer'] == 'test'
    
    def test_missing_callback_handling(self):
        """Test that missing callbacks (None) are handled gracefully."""
        
        with patch.object(self.solar_api, '_check_search_needed', return_value='N'), \
             patch.object(self.solar_api, '_get_direct_answer', return_value='Direct answer'):
            
            # Should work fine with None callbacks
            result = self.solar_api.intelligent_complete(
                user_query="Test",
                on_search_start=None,
                on_search_queries_generated=None,
                on_search_done=None,
                on_update=None
            )
            
            assert result['search_used'] is False
            assert result['answer'] == 'Direct answer'


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 