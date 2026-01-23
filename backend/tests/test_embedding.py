
import asyncio
import os
import sys
from datetime import datetime

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ai.embedding_service import EmbeddingService

async def test_embedding_service():
    print("\n=== Testing EmbeddingService ===")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("SKIPPING: No OPENROUTER_API_KEY found")
        return

    service = EmbeddingService(api_key=api_key)
    
    # Test 1: Single embedding
    text = "Will Donald Trump win the 2024 US Election?"
    print(f"Embedding: '{text}'")
    emb = await service.embed(text)
    print(f"Vector dim: {len(emb)}")
    assert len(emb) == 1536, "Embedding dimension mismatch"
    
    # Test 2: Similarity
    text2 = "Who will be the next president of USA in 2024?"
    text3 = "Is Bitcoin going to hit 100k?"
    
    emb2 = await service.embed(text2)
    emb3 = await service.embed(text3)
    
    score_related = service.cosine_similarity(emb, emb2)
    score_unrelated = service.cosine_similarity(emb, emb3)
    
    print(f"Similarity (Related): {score_related:.4f}")
    print(f"Similarity (Unrelated): {score_unrelated:.4f}")
    
    assert score_related > score_unrelated, "Related text should have higher score"
    assert score_related > 0.6, "Related text score too low"
    
    # Test 3: Find most similar
    candidates = [
        "Will Biden win re-election?",
        "Will Bitcoin hit 100k?",
        "Who will win the 2024 election?",
        "GDP growth 2024"
    ]
    
    match = await service.find_most_similar(text, candidates)
    if match:
        idx, score = match
        print(f"Best match for '{text}': '{candidates[idx]}' (Score: {score:.4f})")
        assert idx == 2, "Wrong match identified"
    else:
        print("No match found")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        asyncio.run(test_embedding_service())
        print("\n✅ Embedding Service Tests Passed")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
