import requests
from typing import List, Dict
from datetime import datetime, timedelta

def fetch_gdelt2(query: str, limit: int = 20, **kwargs) -> List[Dict]:
    """
    Fetch news articles from GDELT 2.0 using keyword search.
    Ensures the requested `limit` is actually returned by paginating results.

    Signature:
        fetch_gdelt2(query: str, limit: int = 20, **kwargs) -> List[Dict]
    """
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    today = datetime.utcnow()
    start_date = kwargs.get("start_date", (today - timedelta(days=7)).strftime("%Y%m%d%H%M%S"))
    end_date = kwargs.get("end_date", today.strftime("%Y%m%d%H%M%S"))

    articles: List[Dict] = []
    startrecord = 0
    batch_size = min(limit, 250)  # GDELT allows up to 250 per request

    while len(articles) < limit:
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "JSON",
            "maxrecords": batch_size,
            "startdatetime": start_date,
            "enddatetime": end_date,
            "startrecord": startrecord,
            "sourcelang": "english",
        }

        try:
            resp = requests.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        batch = data.get("articles", [])
        if not batch:
            break  # no more results

        for item in batch:
            pub_dt = item.get("seendate") or item.get("date")
            if pub_dt:
                try:
                    pub_dt = datetime.strptime(pub_dt, "%Y%m%d%H%M%S").isoformat()
                except Exception:
                    pub_dt = pub_dt

            articles.append({
                "source": "gdelt2",
                "title": item.get("title") or "",
                "description": item.get("themes") or "",
                "url": item.get("url"),
                "published_at": pub_dt,
                "raw": item,
            })

            if len(articles) >= limit:
                break

        startrecord += len(batch)
        if len(batch) < batch_size:
            break  # no more data to paginate

    return articles[:limit]
