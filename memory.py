import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import re


class MemoryManager:
    """
    Manages conversation memory with automatic summarization when memory exceeds limits.
    
    Features:
    - Stores conversation history with timestamps
    - Tracks word count and automatically summarizes when over 5K words
    - Maintains context for ongoing conversations
    - Persistent storage to file
    """
    
    def __init__(self, memory_file: str = "memory.json", max_words: int = 5000, summary_target: int = 1000, llm_function=None):
        """
        Initialize the memory manager.
        
        Args:
            memory_file (str): Path to the memory storage file
            max_words (int): Maximum words to keep in memory before summarization
            summary_target (int): Target word count after summarization
            llm_function (callable, optional): Function to use for LLM-based summarization
        """
        self.memory_file = memory_file
        self.max_words = max_words
        self.summary_target = summary_target
        self.llm_function = llm_function
        self.memory = {
            "conversations": [],
            "summary": "",
            "last_updated": None,
            "word_count": 0
        }
        self.load_memory()
    
    def add_conversation(self, user_input: str, assistant_response: str, sources: List[Dict] = None, metadata: Dict = None):
        """
        Add a new conversation to memory.
        
        Args:
            user_input (str): The user's input
            assistant_response (str): The assistant's response
            sources (List[Dict], optional): Search sources if any
            metadata (Dict, optional): Additional metadata
        """
        conversation = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "assistant_response": assistant_response,
            "sources": sources or [],
            "metadata": metadata or {}
        }
        
        self.memory["conversations"].append(conversation)
        self.memory["last_updated"] = datetime.now().isoformat()
        self._update_word_count()
        
        # Check if we need to summarize
        if self.memory["word_count"] > self.max_words:
            self._summarize_memory(self.llm_function)
        
        self.save_memory()
    
    def get_context(self, max_context_words: int = 2000) -> str:
        """
        Get recent conversation context for use in new conversations.
        
        Args:
            max_context_words (int): Maximum words to include in context
        
        Returns:
            str: Formatted context string
        """
        context_parts = []
        
        # Add summary if exists
        if self.memory["summary"]:
            context_parts.append(f"Previous conversation summary:\n{self.memory['summary']}\n")
        
        # Add recent conversations
        recent_conversations = self.memory["conversations"][-10:]  # Last 10 conversations
        
        for conv in recent_conversations:
            context_parts.append(f"User: {conv['user_input']}")
            context_parts.append(f"Assistant: {conv['assistant_response'][:500]}...")  # Truncate long responses
            context_parts.append("")  # Empty line for separation
        
        context = "\n".join(context_parts)
        
        # Truncate if too long
        if self._count_words(context) > max_context_words:
            words = context.split()
            truncated_words = words[:max_context_words]
            context = " ".join(truncated_words) + "..."
        
        return context
    
    def clear_memory(self):
        """Clear all memory and reset to initial state."""
        self.memory = {
            "conversations": [],
            "summary": "",
            "last_updated": None,
            "word_count": 0
        }
        self.save_memory()
    
    def get_memory_stats(self) -> Dict:
        """
        Get memory statistics.
        
        Returns:
            Dict: Memory statistics including word count, conversation count, etc.
        """
        return {
            "total_conversations": len(self.memory["conversations"]),
            "word_count": self.memory["word_count"],
            "has_summary": bool(self.memory["summary"]),
            "last_updated": self.memory["last_updated"],
            "memory_file_exists": os.path.exists(self.memory_file)
        }
    
    def export_memory(self, export_file: str = None) -> str:
        """
        Export memory to a file or return as string.
        
        Args:
            export_file (str, optional): File to export to
        
        Returns:
            str: JSON string of memory data
        """
        memory_json = json.dumps(self.memory, indent=2, ensure_ascii=False)
        
        if export_file:
            with open(export_file, 'w', encoding='utf-8') as f:
                f.write(memory_json)
        
        return memory_json
    
    def load_memory(self):
        """Load memory from file if it exists."""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    loaded_memory = json.load(f)
                    # Validate structure
                    if all(key in loaded_memory for key in ["conversations", "summary", "last_updated", "word_count"]):
                        self.memory = loaded_memory
                        self._update_word_count()  # Recalculate word count
                    else:
                        print(f"Invalid memory file format, starting fresh")
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"Error loading memory: {e}, starting fresh")
    
    def save_memory(self):
        """Save memory to file."""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving memory: {e}")
    
    def _update_word_count(self):
        """Update the total word count of all conversations and summary."""
        total_words = 0
        
        # Count words in summary
        if self.memory["summary"]:
            total_words += self._count_words(self.memory["summary"])
        
        # Count words in conversations
        for conv in self.memory["conversations"]:
            total_words += self._count_words(conv["user_input"])
            total_words += self._count_words(conv["assistant_response"])
        
        self.memory["word_count"] = total_words
    
    def _count_words(self, text: str) -> int:
        """Count words in text, handling various languages."""
        if not text:
            return 0
        
        # Simple word counting - split by whitespace and count non-empty strings
        words = text.split()
        return len([word for word in words if word.strip()])
    
    def _summarize_memory(self, llm_function=None):
        """Summarize memory when it exceeds the maximum word limit."""
        # Memory exceeds {self.max_words} words, summarizing...
        
        # Create a simple summary from existing conversations
        if not self.memory["conversations"]:
            return
        
        # If LLM function is provided, use it for better summarization
        if llm_function:
            try:
                self.summarize_with_llm(llm_function)
                return
            except Exception as e:
                print(f"LLM summarization failed, falling back to simple method: {e}")
        
        # Fallback to simple summarization
        # Get the most important conversations (recent ones)
        important_conversations = self.memory["conversations"][-5:]  # Keep last 5 conversations
        older_conversations = self.memory["conversations"][:-5]
        
        # Create summary from older conversations
        if older_conversations:
            summary_parts = []
            if self.memory["summary"]:
                summary_parts.append(self.memory["summary"])
            
            # Add key topics from older conversations
            for conv in older_conversations:
                # Extract key topics (simple heuristic)
                user_input = conv["user_input"][:100]  # First 100 chars
                summary_parts.append(f"Topic: {user_input}")
            
            # Combine and limit summary
            new_summary = " | ".join(summary_parts)
            words = new_summary.split()
            if len(words) > self.summary_target:
                new_summary = " ".join(words[:self.summary_target]) + "..."
            
            self.memory["summary"] = new_summary
        
        # Keep only recent conversations
        self.memory["conversations"] = important_conversations
        self._update_word_count()
        
        # Memory summarized. New word count: {self.memory['word_count']}
    
    def summarize_with_llm(self, llm_function):
        """
        Summarize memory using an LLM function.
        
        Args:
            llm_function (callable): Function that takes a prompt and returns a summary
        """
        if not self.memory["conversations"]:
            return
        
        # Prepare content for summarization
        content_to_summarize = []
        
        # Add existing summary if present
        if self.memory["summary"]:
            content_to_summarize.append(f"Previous summary: {self.memory['summary']}")
        
        # Add conversations to summarize (all except the last few)
        conversations_to_summarize = self.memory["conversations"][:-3]  # Keep last 3 conversations
        
        for conv in conversations_to_summarize:
            content_to_summarize.append(f"User: {conv['user_input']}")
            content_to_summarize.append(f"Assistant: {conv['assistant_response']}")
        
        if not content_to_summarize:
            return
        
        # Create summarization prompt
        content = "\n".join(content_to_summarize)
        prompt = f"""Please create a concise summary of the following conversation history. 
Focus on key topics, important information, and context that would be useful for future conversations.
Keep the summary under {self.summary_target} words.

Conversation History:
{content}

Summary:"""
        
        try:
            # Use the provided LLM function to create summary
            new_summary = llm_function(prompt)
            
            # Update memory with new summary
            self.memory["summary"] = new_summary
            self.memory["conversations"] = self.memory["conversations"][-3:]  # Keep only last 3 conversations
            self._update_word_count()
            
            # Memory summarized with LLM. New word count: {self.memory['word_count']}
            
        except Exception as e:
            print(f"Error during LLM summarization: {e}")
            # Fallback to simple summarization
            self._summarize_memory() 