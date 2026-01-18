"""Embedding Service for semantic text matching using OpenRouter API."""

import os
import math
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

DEBUG_EMBEDDING = True


@dataclass 
class EmbeddingCacheEntry:
    """Cached embedding with expiration."""
    embedding: List[float]
    expires_at: datetime


class EmbeddingService:
    """
    Service for generating text embeddings via OpenRouter.
    Uses OpenAI's text-embedding-3-small model for semantic similarity.
    """
    
    def __init__(self, api_key: Optional[str] = None, cache_ttl_minutes: int = 15):
        """
        Initialize the embedding service.
        
        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            cache_ttl_minutes: How long to cache embeddings (default 15 min)
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
        self.api_url = "https://openrouter.ai/api/v1/embeddings"
        self.model = "openai/text-embedding-3-small"
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        
        # In-memory cache: text -> EmbeddingCacheEntry
        self._cache: Dict[str, EmbeddingCacheEntry] = {}
        self._cache_lock = asyncio.Lock()
        
        if DEBUG_EMBEDDING:
            print(f"[EmbeddingService] Initialized with model: {self.model}")
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent caching."""
        return text.strip().lower()
    
    async def _get_from_cache(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache if not expired."""
        key = self._normalize_text(text)
        async with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if datetime.utcnow() < entry.expires_at:
                    return entry.embedding
                else:
                    del self._cache[key]
        return None
    
    async def _set_cache(self, text: str, embedding: List[float]) -> None:
        """Store embedding in cache."""
        key = self._normalize_text(text)
        entry = EmbeddingCacheEntry(
            embedding=embedding,
            expires_at=datetime.utcnow() + self.cache_ttl
        )
        async with self._cache_lock:
            self._cache[key] = entry
    
    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector (1536 dims)
        """
        # Check cache first
        cached = await self._get_from_cache(text)
        if cached:
            if DEBUG_EMBEDDING:
                print(f"[EmbeddingService] Cache hit for: {text[:40]}...")
            return cached
        
        # Call OpenRouter API
        embeddings = await self._call_api([text])
        embedding = embeddings[0] if embeddings else []
        
        # Cache the result
        if embedding:
            await self._set_cache(text, embedding)
        
        return embedding
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Check cache for each text
        results: List[Optional[List[float]]] = [None] * len(texts)
        texts_to_fetch: List[Tuple[int, str]] = []
        
        for i, text in enumerate(texts):
            cached = await self._get_from_cache(text)
            if cached:
                results[i] = cached
            else:
                texts_to_fetch.append((i, text))
        
        if DEBUG_EMBEDDING:
            print(f"[EmbeddingService] Cache: {len(texts) - len(texts_to_fetch)}/{len(texts)} hits")
        
        # Fetch uncached embeddings
        if texts_to_fetch:
            indices, uncached_texts = zip(*texts_to_fetch)
            new_embeddings = await self._call_api(list(uncached_texts))
            
            # Store in cache and results
            for idx, text, embedding in zip(indices, uncached_texts, new_embeddings):
                results[idx] = embedding
                await self._set_cache(text, embedding)
        
        return [r or [] for r in results]
    
    async def _call_api(self, texts: List[str]) -> List[List[float]]:
        """
        Call OpenRouter embeddings API.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if DEBUG_EMBEDDING:
            print(f"[EmbeddingService] API call for {len(texts)} texts")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://oddbase-dashboard.local",
            "X-Title": "OddBase Prediction Market Dashboard"
        }
        
        data = {
            "model": self.model,
            "input": texts
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json=data
                )
            
            if response.status_code != 200:
                print(f"[EmbeddingService] API error: {response.status_code} - {response.text}")
                return [[] for _ in texts]
            
            result = response.json()
            
            # OpenRouter returns embeddings in 'data' array
            embeddings_data = result.get("data", [])
            
            # Sort by index to maintain order
            embeddings_data.sort(key=lambda x: x.get("index", 0))
            
            embeddings = [item.get("embedding", []) for item in embeddings_data]
            
            if DEBUG_EMBEDDING:
                dims = len(embeddings[0]) if embeddings and embeddings[0] else 0
                print(f"[EmbeddingService] Received {len(embeddings)} embeddings, {dims} dims each")
            
            return embeddings
            
        except Exception as e:
            print(f"[EmbeddingService] API exception: {e}")
            return [[] for _ in texts]
    
    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            a: First embedding vector
            b: Second embedding vector
            
        Returns:
            Similarity score between -1 and 1 (higher = more similar)
        """
        if not a or not b or len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    async def find_most_similar(
        self,
        target_text: str,
        candidate_texts: List[str],
        threshold: float = 0.70
    ) -> Optional[Tuple[int, float]]:
        """
        Find the most similar text from a list of candidates.
        
        Args:
            target_text: The text to match against
            candidate_texts: List of candidate texts to compare
            threshold: Minimum similarity score (default 0.70)
            
        Returns:
            Tuple of (best_index, similarity_score) or None if no match above threshold
        """
        if not candidate_texts:
            return None
        
        # Embed target and all candidates
        all_texts = [target_text] + candidate_texts
        embeddings = await self.embed_batch(all_texts)
        
        target_embedding = embeddings[0]
        candidate_embeddings = embeddings[1:]
        
        if not target_embedding:
            return None
        
        # Find best match
        best_idx = -1
        best_score = 0.0
        
        for i, candidate_emb in enumerate(candidate_embeddings):
            if not candidate_emb:
                continue
            score = self.cosine_similarity(target_embedding, candidate_emb)
            if score > best_score:
                best_score = score
                best_idx = i
        
        if best_idx >= 0 and best_score >= threshold:
            if DEBUG_EMBEDDING:
                print(f"[EmbeddingService] Best match: idx={best_idx}, score={best_score:.3f}")
            return (best_idx, best_score)
        
        return None
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the embedding cache."""
        now = datetime.utcnow()
        valid_count = sum(1 for e in self._cache.values() if e.expires_at > now)
        return {
            "total_cached": len(self._cache),
            "valid_cached": valid_count,
            "expired_cached": len(self._cache) - valid_count,
            "ttl_minutes": self.cache_ttl.total_seconds() / 60
        }
