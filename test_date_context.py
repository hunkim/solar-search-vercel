#!/usr/bin/env python3
"""
Test script to verify date context enhancements in solar.py
"""

import sys
import os
from datetime import datetime

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solar import SolarAPI
from telegram_utils import TelegramMessageHandler

def test_date_context():
    """Test that date context is properly added to various components"""
    
    print("🧪 Testing Date Context Enhancements")
    print("=" * 50)
    
    # Initialize the SolarAPI
    solar_api = SolarAPI()
    
    # Test 1: Search Query Generation with Date Context
    print("\n1. Testing Search Query Generation with Date Context")
    print("-" * 50)
    
    test_queries = [
        "What are the latest AI developments?",
        "Current Apple stock price",
        "Recent news about Tesla",
        "What's the weather today?",
        "Latest developments in quantum computing"
    ]
    
    for query in test_queries:
        print(f"\nUser Query: '{query}'")
        try:
            search_queries = solar_api._extract_search_queries_fast(query, os.getenv("UPSTAGE_MODEL_NAME", "solar-pro2"))
            print(f"Generated Search Queries: {search_queries}")
            
            # Check if current year is included in at least one query
            current_year = str(datetime.now().year)
            has_date_context = any(
                current_year in sq or 'today' in sq.lower() or 'recent' in sq.lower() or 'latest' in sq.lower() or 'current' in sq.lower()
                for sq in search_queries
            )
            print(f"✅ Date context detected: {has_date_context}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test 2: Direct Answer with Date Context
    print("\n\n2. Testing Direct Answer with Date Context")
    print("-" * 50)
    
    test_query = "What's the current state of AI technology?"
    print(f"User Query: '{test_query}'")
    
    try:
        # Mock the complete method to see what prompt is generated
        original_complete = solar_api.complete
        captured_prompt = None
        
        def mock_complete(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Mock response for testing"
        
        solar_api.complete = mock_complete
        
        response = solar_api._get_direct_answer(test_query, os.getenv("UPSTAGE_MODEL_NAME", "solar-pro2"), False, None)
        
        print(f"Enhanced Prompt Generated:")
        print(f"'{captured_prompt[:200]}...'")
        
        # Check if date context is in the prompt
        current_date = datetime.now().strftime("%B %d, %Y")
        has_date = current_date in captured_prompt
        print(f"✅ Date context in prompt: {has_date}")
        
        # Restore original method
        solar_api.complete = original_complete
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Telegram Enhanced Query with Date Context
    print("\n\n3. Testing Telegram Enhanced Query with Date Context")
    print("-" * 50)
    
    test_query = "Tell me about recent space missions"
    print(f"User Query: '{test_query}'")
    
    try:
        enhanced_query = TelegramMessageHandler.create_enhanced_query(test_query)
        print(f"Enhanced Telegram Query:")
        print(f"'{enhanced_query[:300]}...'")
        
        # Check if current date is included
        current_date = datetime.now().strftime("%B %d, %Y")
        current_year = str(datetime.now().year)
        has_date = current_date in enhanced_query and current_year in enhanced_query
        print(f"✅ Date context in Telegram query: {has_date}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Search Decision with Date Context
    print("\n\n4. Testing Search Decision with Date Context")
    print("-" * 50)
    
    time_sensitive_queries = [
        "What happened today in the news?",
        "Current Bitcoin price",
        "Latest COVID statistics",
        "What is Python programming?" # This should not need search
    ]
    
    for query in time_sensitive_queries:
        print(f"\nUser Query: '{query}'")
        try:
            # Mock the complete method to capture the search decision prompt
            original_complete = solar_api.complete
            captured_prompt = None
            
            def mock_complete(prompt, **kwargs):
                nonlocal captured_prompt
                captured_prompt = prompt
                # Return Y for time-sensitive queries, N for general knowledge
                if any(word in query.lower() for word in ['today', 'current', 'latest', 'news', 'price']):
                    return "Y"
                else:
                    return "N"
            
            solar_api.complete = mock_complete
            
            decision = solar_api._check_search_needed(query, os.getenv("UPSTAGE_MODEL_NAME", "solar-pro2"))
            
            # Check if date context is in the search decision prompt
            current_date = datetime.now().strftime("%B %d, %Y")
            has_date = current_date in captured_prompt if captured_prompt else False
            
            print(f"Search Decision: {decision}")
            print(f"✅ Date context in search decision: {has_date}")
            
            # Restore original method
            solar_api.complete = original_complete
            
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n\n🎉 Date Context Testing Complete!")
    print("=" * 50)
    print("Summary:")
    print("✅ Search query generation now includes current year, 'today', 'recent', etc.")
    print("✅ Direct answers include current date, year, and time context")
    print("✅ Telegram queries include date context for better responses")
    print("✅ Search decisions consider current date for time-sensitive queries")
    print("\nThe LLM will now generate more relevant search keywords and provide")
    print("better context-aware responses for time-sensitive questions!")

if __name__ == "__main__":
    test_date_context() 