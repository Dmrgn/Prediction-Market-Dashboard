"""
EXA.ai News Fetcher
Just the wrapper
Notes:
  - EXA requires POST with JSON body.
  - This uses the search endpoint with basic query + num_results.
  - Also can use filters like start_published_date.
"""

import os
import requests
from typing import List, Dict

def fetch_exa(query: str, limit: int = 20, **kwargs) -> List[Dict]:
    api_key = os.getenv("EXA")
    if not api_key:
        return []

    url = "https://api.exa.ai/search"
    headers = {"x-api-key": api_key}
    payload = {
        "query": query,
        "numResults": limit,
        "text": True,
        **kwargs,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    return [
        {
            "source": "exa",
            "title": item.get("title") or item.get("url", ""),
            "description": item.get("snippet"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "raw": item,
        }
        for item in data.get("results", [])
    ]
