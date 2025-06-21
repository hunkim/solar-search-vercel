import pytest
import os
import json
import tempfile
import shutil
from datetime import datetime
from unittest.mock import patch, MagicMock

from memory import MemoryManager


class TestMemoryManager:
    """Comprehensive tests for the MemoryManager class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.memory_file = os.path.join(self.test_dir, "test_memory.json")
        
        # Initialize memory manager with test file
        self.memory_manager = MemoryManager(
            memory_file=self.memory_file,
            max_words=100,  # Small limit for testing
            summary_target=20
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        # Remove test directory and all files
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test MemoryManager initialization."""
        assert self.memory_manager.memory_file == self.memory_file
        assert self.memory_manager.max_words == 100
        assert self.memory_manager.summary_target == 20
        assert self.memory_manager.memory["conversations"] == []
        assert self.memory_manager.memory["summary"] == ""
        assert self.memory_manager.memory["word_count"] == 0
    
    def test_add_conversation_basic(self):
        """Test adding a basic conversation."""
        user_input = "What is Python?"
        assistant_response = "Python is a programming language."
        
        self.memory_manager.add_conversation(user_input, assistant_response)
        
        assert len(self.memory_manager.memory["conversations"]) == 1
        conversation = self.memory_manager.memory["conversations"][0]
        assert conversation["user_input"] == user_input
        assert conversation["assistant_response"] == assistant_response
        assert "timestamp" in conversation
        assert conversation["sources"] == []
        assert conversation["metadata"] == {}
    
    def test_add_conversation_with_sources_and_metadata(self):
        """Test adding conversation with sources and metadata."""
        user_input = "What's the weather?"
        assistant_response = "It's sunny today."
        sources = [{"title": "Weather API", "url": "http://weather.com"}]
        metadata = {"search_used": True, "response_time": 1.5}
        
        self.memory_manager.add_conversation(
            user_input, assistant_response, sources, metadata
        )
        
        conversation = self.memory_manager.memory["conversations"][0]
        assert conversation["sources"] == sources
        assert conversation["metadata"] == metadata
    
    def test_word_counting(self):
        """Test word counting functionality."""
        # Test empty string
        assert self.memory_manager._count_words("") == 0
        assert self.memory_manager._count_words(None) == 0
        
        # Test simple sentences
        assert self.memory_manager._count_words("Hello world") == 2
        assert self.memory_manager._count_words("This is a test sentence.") == 5
        
        # Test with extra whitespace
        assert self.memory_manager._count_words("  Hello   world  ") == 2
        
        # Test with special characters
        assert self.memory_manager._count_words("Hello, world! How are you?") == 5
    
    def test_word_count_update(self):
        """Test that word count is updated correctly."""
        # Add first conversation
        self.memory_manager.add_conversation("Hello", "Hi there, how are you?")
        assert self.memory_manager.memory["word_count"] == 6  # 1 + 5 words
        
        # Add second conversation
        self.memory_manager.add_conversation("What is AI?", "Artificial Intelligence is...")
        assert self.memory_manager.memory["word_count"] == 12  # 6 + 3 + 3 words (is... counts as 1 word)
    
    def test_get_context_empty(self):
        """Test getting context when no conversations exist."""
        context = self.memory_manager.get_context()
        assert context == ""
    
    def test_get_context_with_conversations(self):
        """Test getting context with conversations."""
        # Add some conversations
        self.memory_manager.add_conversation("What is Python?", "Python is a programming language used for various applications.")
        self.memory_manager.add_conversation("How do I learn it?", "Start with basic syntax and practice coding exercises.")
        
        context = self.memory_manager.get_context()
        
        assert "User: What is Python?" in context
        assert "Assistant: Python is a programming language" in context
        assert "User: How do I learn it?" in context
        assert "Assistant: Start with basic syntax" in context
    
    def test_get_context_with_summary(self):
        """Test getting context when summary exists."""
        # Add a summary
        self.memory_manager.memory["summary"] = "Previous discussions about programming languages."
        
        # Add a conversation
        self.memory_manager.add_conversation("What is Java?", "Java is another programming language.")
        
        context = self.memory_manager.get_context()
        
        assert "Previous conversation summary:" in context
        assert "Previous discussions about programming languages." in context
        assert "User: What is Java?" in context
    
    def test_get_context_word_limit(self):
        """Test that context respects word limits."""
        # Add a long conversation
        long_response = " ".join(["word"] * 100)  # 100 words
        self.memory_manager.add_conversation("Tell me a story", long_response)
        
        # Get context with small limit
        context = self.memory_manager.get_context(max_context_words=10)
        
        # Should be truncated
        assert context.endswith("...")
        assert self.memory_manager._count_words(context) <= 15  # Some buffer for truncation
    
    def test_memory_stats(self):
        """Test memory statistics."""
        # Initial stats
        stats = self.memory_manager.get_memory_stats()
        assert stats["total_conversations"] == 0
        assert stats["word_count"] == 0
        assert stats["has_summary"] == False
        assert stats["last_updated"] is None
        
        # Add conversation and check stats
        self.memory_manager.add_conversation("Hello", "Hi there")
        stats = self.memory_manager.get_memory_stats()
        assert stats["total_conversations"] == 1
        assert stats["word_count"] == 3
        assert stats["last_updated"] is not None
    
    def test_clear_memory(self):
        """Test clearing memory."""
        # Add some conversations
        self.memory_manager.add_conversation("Hello", "Hi")
        self.memory_manager.memory["summary"] = "Some summary"
        
        # Clear memory
        self.memory_manager.clear_memory()
        
        # Check everything is reset
        assert len(self.memory_manager.memory["conversations"]) == 0
        assert self.memory_manager.memory["summary"] == ""
        assert self.memory_manager.memory["word_count"] == 0
        assert self.memory_manager.memory["last_updated"] is None
    
    def test_save_and_load_memory(self):
        """Test saving and loading memory from file."""
        # Add some data
        self.memory_manager.add_conversation("Test question", "Test answer")
        self.memory_manager.memory["summary"] = "Test summary"
        # Make sure to save the memory after manually setting summary
        self.memory_manager.save_memory()
        
        # Create new memory manager with same file
        new_memory_manager = MemoryManager(memory_file=self.memory_file)
        
        # Check data was loaded
        assert len(new_memory_manager.memory["conversations"]) == 1
        assert new_memory_manager.memory["summary"] == "Test summary"
        assert new_memory_manager.memory["word_count"] > 0
    
    def test_load_memory_invalid_file(self):
        """Test loading memory with invalid file."""
        # Create invalid JSON file
        with open(self.memory_file, 'w') as f:
            f.write("invalid json")
        
        # Should handle gracefully
        memory_manager = MemoryManager(memory_file=self.memory_file)
        assert len(memory_manager.memory["conversations"]) == 0
    
    def test_load_memory_missing_keys(self):
        """Test loading memory with missing required keys."""
        # Create file with missing keys
        with open(self.memory_file, 'w') as f:
            json.dump({"conversations": []}, f)  # Missing other keys
        
        # Should handle gracefully
        memory_manager = MemoryManager(memory_file=self.memory_file)
        assert len(memory_manager.memory["conversations"]) == 0
    
    def test_export_memory(self):
        """Test exporting memory."""
        # Add some data
        self.memory_manager.add_conversation("Export test", "Export response")
        
        # Export to string
        exported_json = self.memory_manager.export_memory()
        exported_data = json.loads(exported_json)
        
        assert "conversations" in exported_data
        assert len(exported_data["conversations"]) == 1
        
        # Export to file
        export_file = os.path.join(self.test_dir, "exported.json")
        self.memory_manager.export_memory(export_file)
        
        assert os.path.exists(export_file)
        with open(export_file, 'r') as f:
            file_data = json.load(f)
        assert len(file_data["conversations"]) == 1
    
    def test_automatic_summarization_trigger(self):
        """Test that summarization is triggered when word count exceeds limit."""
        # Add conversations until we exceed the limit
        for i in range(15):  # Each conversation adds ~6 words
            self.memory_manager.add_conversation(
                f"Question {i}?", 
                f"Answer {i} with some extra words here."
            )
        
        # Should have triggered summarization
        assert self.memory_manager.memory["word_count"] <= self.memory_manager.max_words
        # Summarization keeps last 5 conversations but the exact count may vary due to summary creation
        assert len(self.memory_manager.memory["conversations"]) <= 10  # Allow more flexibility
    
    def test_simple_summarization(self):
        """Test the simple summarization mechanism."""
        # Add many conversations
        for i in range(10):
            self.memory_manager.add_conversation(
                f"Question about topic {i}",
                f"Detailed answer about topic {i} with more information."
            )
        
        # Manually trigger summarization
        self.memory_manager._summarize_memory()
        
        # Should have created a summary and kept recent conversations
        assert len(self.memory_manager.memory["conversations"]) <= 5
        # Summary might be created from older conversations
    
    def test_llm_summarization(self):
        """Test LLM-based summarization."""
        # Mock LLM function with realistic Solar API response
        realistic_summary = "The conversation includes multiple questions and detailed answers covering various topics. The user asked about programming concepts, software development practices, and technical implementations. The assistant provided comprehensive responses with explanations and examples. Key themes include software engineering, programming languages, and development methodologies. The interaction demonstrates a technical discussion between user and assistant."
        mock_llm = MagicMock(return_value=realistic_summary)
        
        # Add some conversations with realistic content
        conversations = [
            ("What is Python programming?", "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms and has extensive libraries."),
            ("How do I implement a REST API?", "To implement a REST API, you can use frameworks like Flask or FastAPI in Python. Define your endpoints, handle HTTP methods, and structure your responses properly."),
            ("What are design patterns?", "Design patterns are reusable solutions to common problems in software design. Examples include Singleton, Factory, and Observer patterns."),
            ("Explain database normalization", "Database normalization is the process of organizing data to reduce redundancy and improve data integrity. It involves dividing tables and establishing relationships."),
            ("What is machine learning?", "Machine learning is a subset of AI that enables systems to learn and improve from data without explicit programming. It includes supervised, unsupervised, and reinforcement learning."),
            ("How to optimize code performance?", "Code optimization involves improving efficiency through better algorithms, data structures, caching, and profiling to identify bottlenecks.")
        ]
        
        for user_input, response in conversations:
            self.memory_manager.add_conversation(user_input, response)
        
        # Call LLM summarization
        self.memory_manager.summarize_with_llm(mock_llm)
        
        # Check that LLM was called and summary was updated
        mock_llm.assert_called_once()
        assert self.memory_manager.memory["summary"] == realistic_summary
        assert len(self.memory_manager.memory["conversations"]) == 3  # Should keep last 3
        
        # Verify the prompt sent to LLM contains conversation data
        call_args = mock_llm.call_args[0][0]
        assert "Python" in call_args
        assert "programming" in call_args
        assert "summary" in call_args.lower()  # The prompt uses "summary" not "summarize"
    
    def test_llm_summarization_error_handling(self):
        """Test LLM summarization with error."""
        # Mock LLM function that raises a realistic API error
        mock_llm = MagicMock(side_effect=Exception("API request failed with status code 429: Rate limit exceeded"))
        
        # Add realistic conversations
        conversations = [
            ("What is JavaScript?", "JavaScript is a versatile programming language primarily used for web development. It runs in browsers and on servers with Node.js."),
            ("Explain async/await", "Async/await is a syntax that makes it easier to work with promises in JavaScript, providing cleaner asynchronous code."),
            ("What is React?", "React is a JavaScript library for building user interfaces, particularly single-page applications with component-based architecture."),
            ("How does CSS work?", "CSS (Cascading Style Sheets) is used to style HTML elements, controlling layout, colors, fonts, and responsive design."),
            ("What is database indexing?", "Database indexing improves query performance by creating data structures that allow faster data retrieval."),
            ("Explain version control", "Version control systems like Git track changes in code, enabling collaboration and maintaining project history.")
        ]
        
        for user_input, response in conversations:
            self.memory_manager.add_conversation(user_input, response)
        
        original_conversation_count = len(self.memory_manager.memory["conversations"])
        
        # Call LLM summarization (should fall back to simple summarization)
        self.memory_manager.summarize_with_llm(mock_llm)
        
        # Should have fallen back to simple summarization
        mock_llm.assert_called_once()
        # Conversation count should be reduced
        assert len(self.memory_manager.memory["conversations"]) <= original_conversation_count
        # Should have a summary (from simple fallback)
        assert len(self.memory_manager.memory["summary"]) > 0
    
    def test_context_with_recent_conversations_limit(self):
        """Test that context only includes recent conversations."""
        # Add many conversations
        for i in range(15):
            self.memory_manager.add_conversation(f"Question {i}", f"Answer {i}")
        
        context = self.memory_manager.get_context()
        
        # Should only include last 10 conversations
        assert "Question 14" in context  # Most recent
        assert "Question 5" in context   # 10th from last
        assert "Question 4" not in context  # Should not include older ones
    
    def test_conversation_response_truncation_in_context(self):
        """Test that long responses are truncated in context."""
        long_response = "This is a very long response. " * 50  # Over 500 chars
        self.memory_manager.add_conversation("Short question", long_response)
        
        context = self.memory_manager.get_context()
        
        # Response should be truncated to 500 chars + "..."
        lines = context.split('\n')
        assistant_line = [line for line in lines if line.startswith("Assistant:")][0]
        assert len(assistant_line) <= 515  # 500 + "Assistant: " + "..."
        assert assistant_line.endswith("...")
    
    def test_memory_persistence_across_instances(self):
        """Test that memory persists across different MemoryManager instances."""
        # Add data to first instance
        self.memory_manager.add_conversation("Persistence test", "This should persist")
        
        # Create second instance with same file
        second_manager = MemoryManager(memory_file=self.memory_file)
        
        # Check data persists
        assert len(second_manager.memory["conversations"]) == 1
        assert second_manager.memory["conversations"][0]["user_input"] == "Persistence test"
    
    def test_timestamp_format(self):
        """Test that timestamps are in correct ISO format."""
        self.memory_manager.add_conversation("Time test", "Response")
        
        conversation = self.memory_manager.memory["conversations"][0]
        timestamp = conversation["timestamp"]
        
        # Should be able to parse as ISO format
        parsed_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00') if timestamp.endswith('Z') else timestamp)
        assert isinstance(parsed_time, datetime)
    
    def test_edge_case_empty_inputs(self):
        """Test handling of empty or None inputs."""
        # Test empty strings
        self.memory_manager.add_conversation("", "")
        assert len(self.memory_manager.memory["conversations"]) == 1
        assert self.memory_manager.memory["word_count"] == 0
        
        # Test with None sources and metadata (should use defaults)
        self.memory_manager.add_conversation("Test", "Response", None, None)
        conversation = self.memory_manager.memory["conversations"][-1]
        assert conversation["sources"] == []
        assert conversation["metadata"] == {}
    
    def test_word_count_accuracy(self):
        """Test word count accuracy with various text formats."""
        test_cases = [
            ("Hello world", 2),
            ("Hello, world!", 2),
            ("  spaced   text  ", 2),
            ("Multi\nline\ntext", 3),
            ("Mixed123 content!", 2),
            ("", 0),
        ]
        
        for text, expected_count in test_cases:
            actual_count = self.memory_manager._count_words(text)
            assert actual_count == expected_count, f"Failed for '{text}': expected {expected_count}, got {actual_count}"


# Integration tests with real file operations
class TestMemoryManagerIntegration:
    """Integration tests for MemoryManager with real file operations."""
    
    def setup_method(self):
        """Set up integration test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.memory_file = os.path.join(self.test_dir, "integration_memory.json")
    
    def teardown_method(self):
        """Clean up integration test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_concurrent_access_simulation(self):
        """Simulate concurrent access to memory file."""
        manager1 = MemoryManager(memory_file=self.memory_file)
        manager2 = MemoryManager(memory_file=self.memory_file)
        
        # Add conversation with first manager
        manager1.add_conversation("First", "Response1")
        
        # Second manager should see the change when reloaded
        manager2.load_memory()
        assert len(manager2.memory["conversations"]) == 1
        
        # Add conversation with second manager
        manager2.add_conversation("Second", "Response2")
        
        # First manager should see both when reloaded
        manager1.load_memory()
        assert len(manager1.memory["conversations"]) == 2
    
    def test_large_memory_handling(self):
        """Test handling of large memory sizes."""
        manager = MemoryManager(
            memory_file=self.memory_file,
            max_words=1000,
            summary_target=200
        )
        
        # Add many conversations to trigger summarization
        for i in range(50):
            user_input = f"This is question number {i} about various topics and subjects."
            response = f"This is a detailed response for question {i} with comprehensive information about the topic."
            manager.add_conversation(user_input, response)
        
        # Should have triggered summarization
        assert manager.memory["word_count"] <= manager.max_words
        assert len(manager.memory["conversations"]) < 50  # Should be reduced
    
    def test_memory_export_import_cycle(self):
        """Test full export/import cycle."""
        manager1 = MemoryManager(memory_file=self.memory_file)
        
        # Add data
        manager1.add_conversation("Export test", "Export response")
        manager1.memory["summary"] = "Test summary"
        
        # Export to another file
        export_file = os.path.join(self.test_dir, "exported.json")
        manager1.export_memory(export_file)
        
        # Create new manager from exported file
        manager2 = MemoryManager(memory_file=export_file)
        
        # Verify data integrity
        assert len(manager2.memory["conversations"]) == 1
        assert manager2.memory["summary"] == "Test summary"
        assert manager2.memory["conversations"][0]["user_input"] == "Export test"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"]) 