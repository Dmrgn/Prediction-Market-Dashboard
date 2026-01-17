
from dotenv import load_dotenv
from pathlib import Path

# Load .env before importing providers so API keys are available
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from typing import List, Dict, Callable, Generator, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .exa import fetch_exa
from .nd import fetch_newsdata
# from .fmp import fetch_fmp
from .gd import fetch_gdelt2
# from .lc import fetch_lunarcrush
from .cpanic import fetch_cryptopanic

# Article type alias
Article = Dict[str, object]


class NewsFetcher:
    """
    Dispatcher for news provider fetch functions.

    This class contains no provider logic.
    Providers are registered at runtime.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Callable[..., List[Article]]] = {}

    def register_provider(
        self,
        name: str,
        fetch_fn: Callable[..., List[Article]],
    ) -> None:
        """
        Register a news provider fetch function.

        fetch_fn signature:
            (query: str, limit: int, **kwargs) -> List[Article]
        """
        self._providers[name] = fetch_fn

    def available_providers(self) -> List[str]:
        return list(self._providers.keys())

    def fetch(
        self,
        provider: str,
        query: str,
        limit: int = 20,
        **kwargs,
    ) -> List[Article]:
        """
        Fetch news from a single provider.
        """
        if provider not in self._providers:
            raise ValueError(f"Unknown provider: {provider}")

        return self._providers[provider](
            query=query,
            limit=limit,
            **kwargs,
        )

    def fetch_multiple(
        self,
        providers: List[str],
        query: str,
        limit: int = 20,
        **kwargs,
    ) -> List[Article]:
        """
        Fetch news from multiple providers in parallel and aggregate results.
        Uses ThreadPoolExecutor to call all APIs concurrently.
        """
        articles: List[Article] = []
        valid_providers = [p for p in providers if p in self._providers]
        
        if not valid_providers:
            return []

        for _, result in self.fetch_multiple_iter(
            providers=valid_providers,
            query=query,
            limit=limit,
            **kwargs,
        ):
            articles.extend(result)

        return articles

    def fetch_multiple_iter(
        self,
        providers: List[str],
        query: str,
        limit: int = 20,
        **kwargs,
    ) -> Generator[Tuple[str, List[Article]], None, None]:
        """
        Fetch news from multiple providers in parallel and yield results
        as each provider completes.
        """
        valid_providers = [p for p in providers if p in self._providers]

        if not valid_providers:
            return

        def fetch_from_provider(provider: str) -> List[Article]:
            try:
                return self._providers[provider](
                    query=query,
                    limit=limit,
                    **kwargs,
                )
            except Exception as e:
                print(f"[NewsFetcher] Error with {provider}: {e}")
                return []

        with ThreadPoolExecutor(max_workers=len(valid_providers)) as executor:
            future_to_provider = {
                executor.submit(fetch_from_provider, provider): provider
                for provider in valid_providers
            }

            for future in as_completed(future_to_provider):
                provider = future_to_provider[future]
                try:
                    result = future.result()
                    print(f"[NewsFetcher] {provider} returned {len(result)} articles")
                    yield provider, result
                except Exception as e:
                    print(f"[NewsFetcher] {provider} failed: {e}")
                    yield provider, []


news_fetcher = NewsFetcher()

news_fetcher.register_provider("exa", fetch_exa)
news_fetcher.register_provider("newsdata", fetch_newsdata)
news_fetcher.register_provider("gdet", fetch_gdelt2)
news_fetcher.register_provider("cpanic", fetch_cryptopanic)

if __name__ == "__main__":


    print("Testing APIs")
    print("-------------")

    query = "BTC"

    for provider in news_fetcher.available_providers():
        print("┌────────────────────────┐")
        print(f"Trying {provider}...")
        try:
            results = news_fetcher.fetch(
                provider=provider,
                query=query,
                limit=5,
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            print("└────────────────────────┘\n")
            continue

        if not results:
            print(f"[{provider}] no results")
            print("└────────────────────────┘\n")
            continue

        article = results[0]
        title = article.get("title")
        url = article.get("url")

        print(f"[{provider}] {title}")
        print(f"    {url}")
        print("└────────────────────────┘\n")

    print("Tested APIS")
    print("-------------")

