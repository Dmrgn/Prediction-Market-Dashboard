from pathlib import Path
from dotenv import load_dotenv

# since .env file is in the root
load_dotenv(Path(__file__).parent.parent / ".env")

from typing import List, Optional, Union
import json
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from news.fetcher import news_fetcher, Article
from news.rank import rank_articles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}

@app.get("/news/search", response_model=List[Article])
def search_news(
    q: str = Query(..., description="Search query"),
    providers: Optional[List[str]] = Query(
        None, description="Providers to query"
    ),
    limit: int = Query(20, ge=1, le=100),
    stream: bool = Query(False, description="Stream results as they arrive"),
):
    """
    Called when the user presses Enter in the search bar.
    Expected Request shape:
    GET /news/search?q=inflation&providers=newsapi&providers=gnews&limit=25
    
    Returns ranked, deduplicated articles from all providers.
    """
    
    selected_providers = providers or news_fetcher.available_providers()

    if stream:
        def event_stream():
            aggregated: List[Article] = []
            last_ranked: List[Article] = []

            for provider, result in news_fetcher.fetch_multiple_iter(
                providers=selected_providers,
                query=q,
                limit=limit,
            ):
                if result:
                    aggregated.extend(result)

                last_ranked = rank_articles(aggregated, dedupe=True, limit=limit)
                payload = {
                    "provider": provider,
                    "articles": last_ranked,
                }
                yield f"event: update\ndata: {json.dumps(payload)}\n\n"

            yield f"event: done\ndata: {json.dumps({'articles': last_ranked})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Fetch from all providers in parallel (blocking)
    raw_articles = news_fetcher.fetch_multiple(
        providers=selected_providers,
        query=q,
        limit=limit,
    )

    # Rank, dedupe, and limit results
    ranked = rank_articles(raw_articles, dedupe=True, limit=limit)

    return ranked
