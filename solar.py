import requests
import json
import sseclient
import os
from datetime import datetime
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables from .env.local if it exists
load_dotenv('.env.local')

class SolarAPI:
    def __init__(self, api_key=os.getenv("UPSTAGE_API_KEY"), base_url="https://api.upstage.ai/v1/chat/completions"):
        """Initialize the SolarAPI client with the API key.
        
        Args:
            api_key (str): Your Upstage API key
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        # Initialize citation manager
        from citations import CitationManager
        self.citation_manager = CitationManager(self)
    
    def intelligent_complete(self, user_query, model="solar-pro-nightly", stream=False, on_update=None, on_search_start=None, on_search_done=None, on_search_queries_generated=None):
        """
        Intelligently complete a user query by determining if web search is needed,
        and providing either direct answers or search-grounded responses.
        
        Args:
            user_query (str): The user's input query
            model (str): The model to use for completions
            stream (bool): Whether to stream the final response
            on_update (callable): Function to call with each update when streaming
            on_search_start (callable): Function to call when search process starts
            on_search_done (callable): Function to call when search is completed with sources
            on_search_queries_generated (callable): Function to call when search queries are generated
        
        Returns:
            dict: Response with 'answer', 'search_used' (bool), and 'sources' (if search was used)
        """
        
        # Step 1: Start concurrent processes for search decision and query extraction
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Future 1: Check if search is needed (Y/N) - fastest decision
            search_needed_future = executor.submit(
                self._check_search_needed, user_query, model
            )
            
            # Future 2: Extract search queries (run in parallel with decision)
            search_queries_future = executor.submit(
                self._extract_search_queries_fast, user_query, model
            )
            
            # Wait for both the search decision and queries to be ready
            search_needed = search_needed_future.result()
            
            if search_needed.upper().strip() == 'Y':
                # Search is needed - notify and get queries immediately
                if on_search_start:
                    try:
                        on_search_start()
                    except Exception as e:
                        print(f"Error in on_search_start callback: {e}")
                
                # Get search queries and show them to user immediately
                search_queries = search_queries_future.result()
                
                # Show search queries to user right away for best UX
                if on_search_queries_generated:
                    try:
                        on_search_queries_generated(search_queries)
                    except Exception as e:
                        print(f"Error in on_search_queries_generated callback: {e}")
                
                # Now perform the actual search and get grounded response
                response_data = self._get_search_grounded_response(
                    user_query, search_queries, model, stream, on_update, on_search_done
                )
                
                return {
                    'answer': response_data['response'],
                    'search_used': True,
                    'sources': response_data.get('sources', [])
                }
            else:
                # No search needed - cancel search queries and get direct answer
                search_queries_future.cancel()
                
                # Start the direct answer now (we didn't start it earlier to save resources)
                direct_answer_future = executor.submit(
                    self._get_direct_answer, user_query, model, stream, on_update
                )
                
                # Get the direct answer
                direct_answer = direct_answer_future.result()
                
                return {
                    'answer': direct_answer,
                    'search_used': False,
                    'sources': []
                }
    
    def _check_search_needed(self, user_query, model):
        """Check if the user query requires web search. Returns Y or N."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "December 13, 2024"
        
        prompt = f"""Determine if this user query requires current/recent information from web search to provide a complete and accurate answer.

TODAY'S DATE: {current_date}

User Query: "{user_query}"

Consider:
- Does it ask about recent events, news, or current affairs?
- Does it require real-time data (stock prices, weather, sports scores)?
- Does it ask about recent developments in technology, politics, or other rapidly changing fields?
- Does it require information that might have changed recently?
- Does it use time-sensitive terms like "today", "recent", "latest", "current", "now"?
- Does it ask about events that happened after my training data cutoff?

Return ONLY a single character: Y (if web search is needed) or N (if general knowledge is sufficient).

Examples:
- "What is the capital of France?" → N
- "How do I implement a binary search in Python?" → N  
- "What are the latest developments in AI?" → Y
- "What is the current stock price of Apple?" → Y
- "What happened today in the news?" → Y
- "What's the weather today?" → Y
- "Who won the recent elections in South Korea?" → Y
- "Explain quantum computing" → N
- "What are today's trending topics?" → Y

Answer (Y or N only):"""

        try:
            response = self.complete(prompt, model=model, stream=False)
            # Extract just the Y or N from the response
            clean_response = response.strip().upper()
            if 'Y' in clean_response[:3]:  # Look for Y in first 3 characters
                return 'Y'
            elif 'N' in clean_response[:3]:  # Look for N in first 3 characters  
                return 'N'
            else:
                # Default to N if unclear
                return 'N'
        except Exception as e:
            print(f"Error checking search needed: {e}")
            return 'N'  # Default to no search on error
    
    def _get_direct_answer(self, user_query, model, stream, on_update):
        """Get direct answer from LLM without search."""
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "December 13, 2024"
            current_year = datetime.now().year
            current_time = datetime.now().strftime("%I:%M %p %Z")  # e.g., "2:30 PM UTC"
            
            # Enhanced prompt with date context
            enhanced_prompt = f"""Today's date: {current_date}
Current year: {current_year}
Current time: {current_time}

User question: {user_query}

Please provide a comprehensive answer to the user's question. If the question relates to current events, recent developments, or time-sensitive information, please note that your knowledge has a cutoff date and you may not have the most recent information. For such queries, recommend that the user search for the latest information online.

Answer:"""
            
            return self.complete(enhanced_prompt, model=model, stream=stream, on_update=on_update)
        except Exception as e:
            print(f"Error getting direct answer: {e}")
            return f"I apologize, but I encountered an error processing your request: {str(e)}"
    
    def _extract_search_queries_fast(self, user_query, model):
        """Extract 2-3 search queries optimized for web search."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "December 13, 2024"
        current_year = datetime.now().year
        current_month = datetime.now().strftime("%B %Y")  # e.g., "December 2024"
        
        prompt = f"""Extract 2-3 concise search queries from this user question that would get the most relevant web search results.

TODAY'S DATE: {current_date}
CURRENT YEAR: {current_year}
CURRENT MONTH: {current_month}

User Question: "{user_query}"

Rules:
- Make queries specific and focused on key terms
- Remove filler words, focus on essential keywords  
- Include technical terms and proper nouns
- For comparisons, create separate queries for each item
- Keep queries short but comprehensive
- ADD DATE CONTEXT when relevant:
  * Use "{current_year}" for recent/latest queries
  * Use "today", "recent", "latest" for time-sensitive topics
  * Use current month/year for very recent events
  * Include "news" for current events
  * Add "stock price today" for financial queries
  * Use "current" for real-time data requests

Return ONLY a JSON array: ["query1", "query2", "query3"]

Examples:
- "What are the latest AI developments?" → ["latest AI developments {current_year}", "artificial intelligence recent advances news", "AI breakthrough {current_month}"]
- "Compare iPhone vs Samsung" → ["iPhone 15 specifications features {current_year}", "Samsung Galaxy S24 specs {current_year}", "iPhone Samsung comparison {current_year}"]
- "What's the weather today?" → ["weather today current conditions", "weather forecast {current_date.split(',')[0]}", "current weather conditions"]
- "Recent news about Tesla" → ["Tesla news {current_year}", "Tesla recent developments {current_month}", "Tesla latest news today"]
- "Current Apple stock price" → ["Apple stock price today", "AAPL current stock price {current_year}", "Apple share price latest"]

JSON array:"""

        try:
            response = self.complete(prompt, model=model, stream=False)
            # Try to parse JSON from response
            import re
            json_match = re.search(r'\[(.*?)\]', response, re.DOTALL)
            if json_match:
                json_str = '[' + json_match.group(1) + ']'
                queries = json.loads(json_str)
                return queries[:3]  # Limit to 3 queries
            else:
                # Fallback: use the original query
                return [user_query]
        except Exception as e:
            print(f"Error extracting search queries: {e}")
            return [user_query]  # Fallback to original query
    
    def _get_search_grounded_response(self, user_query, search_queries, model, stream, on_update, on_search_done):
        """Get search-grounded response using the provided search queries."""
        try:
            # Use direct API calls instead of tavily-python library
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            if not tavily_api_key:
                print("TAVILY_API_KEY not set, using mock search results")
                # Return mock results for testing
                sources = [
                    {
                        "id": 1,
                        "title": "Mock Search Result",
                        "url": "https://example.com/mock",
                        "content": "This is a mock search result for testing purposes.",
                        "score": 0.9,
                        "published_date": datetime.now().strftime("%Y-%m-%d")
                    }
                ]
                if on_search_done:
                    try:
                        on_search_done(sources)
                    except Exception as e:
                        print(f"Error in on_search_done callback: {e}")
                
                response_text = self._get_direct_answer(user_query, model, stream, on_update)
                return {
                    'response': response_text + " (Note: Using mock data - set TAVILY_API_KEY for real search)",
                    'sources': sources
                }
            
            # Collect search results for each query using CONCURRENT API calls
            all_search_results = []
            
            # Use ThreadPoolExecutor to execute search queries concurrently
            with ThreadPoolExecutor(max_workers=3) as search_executor:
                # Submit all search queries concurrently
                search_futures = []
                for query in search_queries[:3]:  # Limit to 3 queries
                    print(f"Searching for: {query}")
                    future = search_executor.submit(self._tavily_search, query, tavily_api_key)
                    search_futures.append(future)
                
                # Collect results as they complete
                for future in search_futures:
                    search_response = future.result()
                    all_search_results.extend(search_response.get('results', []))
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_results = []
            for result in all_search_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            print(f"Found {len(unique_results)} unique search results")
            
            # Format search results as context
            search_context = ""
            sources = []
            for i, result in enumerate(unique_results[:15], 1):  # Limit to top 15 results
                title = result.get('title', 'No Title')
                content = result.get('content', result.get('raw_content', 'No Content'))
                url = result.get('url', 'No URL')
                search_context += f"[{i}]. {title}\n{content}\n\n"
                
                # Save source metadata
                sources.append({
                    "id": i,
                    "title": title,
                    "url": url,
                    "content": content,
                    "score": result.get('score', 0),
                    "published_date": result.get('published_date', 'No Date')
                })
            
            # Call search done callback
            if on_search_done:
                try:
                    on_search_done(sources)
                except Exception as e:
                    print(f"Error in on_search_done callback: {e}")
            
            # Create grounded prompt with enhanced date context
            current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "December 13, 2024"
            current_year = datetime.now().year
            current_time = datetime.now().strftime("%I:%M %p %Z")  # e.g., "2:30 PM UTC"
            
            grounded_prompt = f"""Use the following search results to answer the user's question comprehensively.

TODAY'S DATE: {current_date}
CURRENT YEAR: {current_year} 
CURRENT TIME: {current_time}

SEARCH RESULTS:
{search_context}

USER QUESTION: {user_query}

INSTRUCTIONS:
1. Respond in the SAME LANGUAGE as the user's question
2. Be comprehensive but concise - provide complete information without being wordy
3. Use information from the search results to provide current, accurate details
4. Add citation numbers [1], [2], etc. after specific facts from the sources
5. Consider the current date when interpreting "recent", "latest", "today", etc.
6. If discussing time-sensitive information, mention when the information was published if available
7. If search results don't contain relevant information, briefly state that
8. For financial data, stock prices, or real-time information, note the time sensitivity

Provide a well-structured, informative answer based on the search results:"""
            
            # Get the grounded response
            response_text = self.complete(grounded_prompt, model=model, stream=stream, on_update=on_update)
            
            return {
                'response': response_text,
                'sources': sources
            }
            
        except Exception as e:
            print(f"Error in search grounding: {e}")
            # Fallback to direct answer
            return {
                'response': self._get_direct_answer(user_query, model, stream, on_update),
                'sources': []
            }
    
    def _tavily_search(self, query, api_key, max_results=8):
        """Direct API call to Tavily search without using their Python library."""
        try:
            url = "https://api.tavily.com/search"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_raw_content": True
            }
            
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Tavily API error: {response.status_code} - {response.text}")
                return {"results": []}
                
        except Exception as e:
            print(f"Error calling Tavily API: {e}")
            return {"results": []}
    
    def complete(self, prompt, model=None, stream=False, on_update=None, search_grounding=False, return_sources=False, search_done_callback=None):
        """Send a completion request to the Solar API.
        
        Args:
            prompt (str): The user's input prompt
            model (str): The model to use
            stream (bool): Whether to stream the response
            on_update (callable): Function to call with each update when streaming
                                 Should accept one argument (the new token/content)
            search_grounding (bool): Whether to ground responses using Tavily search results
            return_sources (bool): Whether to return search result sources along with the response
            search_done_callback (callable): Function to call when search is completed
                                           Should accept one argument (the search results)
        
        Returns:
            str or dict: The complete response text (non-streaming) or a dict with response and sources if return_sources=True
        """
        # If search grounding is enabled, use search results to augment the prompt
        sources = []
        if search_grounding:
            try:
                # Use direct API calls instead of tavily-python library
                tavily_api_key = os.getenv("TAVILY_API_KEY")
                if not tavily_api_key:
                    print("TAVILY_API_KEY not set, proceeding without search grounding")
                    # Call the callback with empty results
                    if search_done_callback:
                        search_done_callback([])
                else:
                    # Get search queries from the prompt
                    if False:
                        queries_json = extract_search_queries(prompt)
                        queries = json.loads(queries_json)["search_queries"]
                        print(f"Search queries: {queries}")
                    else:
                        queries = [prompt]

                    # Collect search results for each query using CONCURRENT API calls
                    all_search_results = []
                    
                    # Use ThreadPoolExecutor to execute search queries concurrently
                    with ThreadPoolExecutor(max_workers=3) as search_executor:
                        # Submit all search queries concurrently
                        search_futures = []
                        for query in queries[:3]:
                            print(f"Searching for {query}")
                            future = search_executor.submit(self._tavily_search, query, tavily_api_key, 10)
                            search_futures.append(future)
                        
                        # Collect results as they complete
                        for future in search_futures:
                            search_response = future.result()
                            print(f"Search response length: {len(search_response.get('results', []))}")
                            all_search_results.extend(search_response.get('results', []))
                            print(f"All search results length: {len(all_search_results)}")
                    
                    # remove duplicates if the URL is the same
                    all_search_results = [result for n, result in enumerate(all_search_results) if result not in all_search_results[n + 1:]]
                    print(f"All search results length after removing duplicates: {len(all_search_results)}")

                    # Format search results as context
                    search_context = ""
                    for i, result in enumerate(all_search_results, 1):  # Limit to top 10 results
                        title = result.get('title', 'No Title')
                        content = result.get('content', result.get('raw_content', 'No Content'))
                        url = result.get('url', 'No URL')
                        search_context += f"[{i}]. {title}\n{content}\n\n"
                        
                        # Save source metadata for return if needed
                        sources.append({
                            "id": i,
                            "title": title,
                            "url": url,
                            "content": content,
                            "score": result.get('score', 0),
                            "published_date": result.get('published_date', 'No Date')
                        })
                    
                    # Create a grounded prompt with the search results
                    grounded_prompt = f"""Use the following search results to help answer the user's question.
---                
SEARCH RESULTS:
{search_context}
---
USER QUESTION: {prompt}

---
IMPORTANT INSTRUCTIONS:
1. Respond in the SAME LANGUAGE as the user's question. If the question is in Korean, respond in Korean.
2. Be BRIEF and CONCISE - this is for Telegram, so get to the point clearly.
3. Make FULL USE of the search results and use terms from the search results in your response.
4. Add citation numbers [1], [2], etc. directly after the specific word or sentence that uses information from the sources. Add citations only for highly relevant information derived from the sources.
5. Consider TIME-SENSITIVITY - today's date is {datetime.now().strftime("%Y-%m-%d")}.

Provide a direct, informative answer based on the search results. If the search results don't contain relevant information, briefly state that you don't have sufficient information to answer the question.

Keep your tone friendly but efficient.
"""
                    
                    prompt = grounded_prompt
                    
                    # Call the search done callback if provided
                    if search_done_callback:
                        search_done_callback(sources)
                    
            except Exception as e:
                print(f"Search grounding failed: {str(e)}. Falling back to standard completion.")
                # Call the callback with empty results if there was an error
                if search_done_callback:
                    search_done_callback([])
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "stream": stream
        }

        if stream:
            response_text = self._stream_request(payload, on_update)
        else:
            response_text = self._standard_request(payload)
            
        # Return response with sources if requested
        if return_sources and search_grounding:
            return {
                "response": response_text,
                "sources": sources
            }
        else:
            return response_text
    
    # Citation methods are now handled by the citation_manager
    def add_citations(self, response_text, sources):
        """Delegate to citation manager."""
        return self.citation_manager.add_citations(response_text, sources)
    
    def fill_citation_heuristic(self, response_text, sources):
        """Delegate to citation manager."""
        return self.citation_manager.fill_citation_heuristic(response_text, sources)
    
    def fill_citation(self, response_text, sources, model="solar-pro-nightly"):
        """Delegate to citation manager."""
        return self.citation_manager.fill_citation(response_text, sources, model)
    
    def _standard_request(self, payload):
        """Make a standard non-streaming request."""
        response = requests.post(
            self.base_url,
            headers=self.headers,
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    
    def _stream_request(self, payload, on_update):
        """Make a streaming request and process the server-sent events."""
        response = requests.post(
            self.base_url,
            headers=self.headers,
            json=payload,
            stream=True
        )
        
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        # Create an SSE client from the response
        client = sseclient.SSEClient(response)
        
        # Full content accumulated across all chunks
        full_content = ""
        chunk_count = 0
        
        for event in client.events():
            if event.data == "[DONE]":
                break
                
            try:
                chunk = json.loads(event.data)
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        content = delta["content"]
                        full_content += content
                        chunk_count += 1
                        
                        # Call the callback function with the new content
                        if on_update:
                            on_update(content)
            except json.JSONDecodeError:
                pass
        
        return full_content


# Simple usage demo
if __name__ == "__main__":
    import os
    
    # Initialize Solar API
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        api_key = input("Enter your Upstage API key: ")
    
    solar = SolarAPI(api_key)
    
    print("=== Solar API Demo ===\n")
    
    # Example 1: Basic completion
    print("1. Basic completion:")
    response = solar.complete("What is the capital of France?")
    print(f"Response: {response}\n")
    
    # Example 2: Intelligent completion (auto decides search vs direct)
    print("2. Intelligent completion:")
    result = solar.intelligent_complete("What are the latest AI developments?")
    print(f"Answer: {result['answer'][:200]}...")
    print(f"Search used: {result['search_used']}")
    print(f"Sources found: {len(result['sources'])}\n")
    
    # Example 3: Streaming response
    print("3. Streaming response:")
    print("Question: How does machine learning work?")
    print("Answer: ", end="")
    
    def print_update(content):
        print(content, end="", flush=True)
    
    solar.complete("How does machine learning work?", stream=True, on_update=print_update)
    print("\n")