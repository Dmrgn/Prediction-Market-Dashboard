import os
import requests
from typing import List, Dict
from datetime import datetime

def fetch_cryptopanic(query: str, limit: int = 20, **kwargs) -> List[Dict]:
    api_key = os.getenv("CPANIC")
    if not api_key:
        print("[CryptoPanic] Error: CPANIC env var is missing")
        return []

    # 1. USE V2 ENDPOINT (Per your docs)
    url = "https://cryptopanic.com/api/developer/v2/posts/"
    
    params = {
        "auth_token": api_key,
        "currencies": query.upper(),
        "kind": "news",
        "public": "true",   # Docs: "Ideal for public-facing... apps"
        **kwargs
    }

    # Remove 'filter' if it's causing empty results, user can pass it in kwargs if needed
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[CryptoPanic] Error: {e}")
        if 'resp' in locals():
            print(f"  Target: {resp.url}")
            print(f"  Response: {resp.text[:200]}")
        return []

    articles: List[Dict] = []
    
    # Docs: Response object has "results": [ ... ]
    for item in data.get("results", [])[:limit]:
        
        # Parse Date (ISO 8601)
        published_at = item.get("published_at")
        if published_at:
            try:
                # API returns "2026-01-17T16:17:47Z" format usually
                dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                published_at = dt.isoformat()
            except ValueError:
                pass 

        articles.append({
            "source": "cryptopanic",
            "title": item.get("title", ""),
            "description": item.get("slug") or "", # 'body' is not always available in basic response
            "url": item.get("url"),
            "published_at": published_at,
            "raw": item,
        })

    return articles
