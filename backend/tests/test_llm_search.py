
import asyncio
import os
import sys

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ai.llm_service import LLMService

async def test_llm_query_generation():
    print("\n=== Testing LLM Search Query Generation ===")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIPPING: No OPENROUTER_API_KEY found")
        return

    service = LLMService(api_key=api_key)
    
    # Test Cases
    cases = [
        ("Will Donald Trump win the 2024 Election?", "polymarket"),
        ("Bitcoin Price > $100k in 2024", "kalshi"),
        ("Fed Interest Rate Decision March 2024", "polymarket")
    ]
    
    for title, platform in cases:
        print(f"\nTarget: '{title}' on {platform}")
        queries = await service.generate_market_search_queries(title, platform)
        print(f"Generated Queries: {queries}")
        
        assert isinstance(queries, list), "Should return a list"
        assert len(queries) > 0, "Should return at least one query"
        assert len(queries) <= 3, "Should return max 3 queries"

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        asyncio.run(test_llm_query_generation())
        print("\n✅ LLM Search Query Tests Passed")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
