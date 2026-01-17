# `News/`

## Purpose

This news module is for news fetching/retrieval/cleaning only. It's basically just API wrappers made for the backend.

`fetcher.py` is **retrieval only**. It does not rank, score, filter, deduplicate, or analyze sentiment.
`rank.py` then handles all ranking, scoring, filtering, deduplication, and sentiment analysis.

## Schema

Every news item returned by the system must conform to the following structure:

```json
{
  "source": "string",
  "title": "string",
  "description": "string | null",
  "url": "string",
  "published_at": "string | int",
  "raw": "object"
}
```

### Field definitions

`source`: ("exai", "newsdata", "FMP", or "lunarcrush").

`title`: Headline text.

`description`: Summary or excerpt if provided. May be null, careful w/ displaying.

`url`: OG article link.

`published_at`: Timestamp as returned by the provider. Normalization is handled later.

`raw`: Original provider payload for traceability and debugging.

## Fetch Model

The system uses a dispatcher pattern:

- Frontend specifies a provider or group of providers.
- The dispatcher routes the request to the appropriate helper function.
- Each helper function returns a list of unified articles.
- Results are concatenated and returned to the caller.

## Supported Query Parameters

All fetchers are expected to accept the following logical inputs:

`query`: Keyword or search string.

`limit`: Maximum number of articles to return per source.

Additional provider-specific parameters are handled internally.
