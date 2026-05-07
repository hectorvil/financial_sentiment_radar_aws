"""Twitter/X recent-search ingestion.

This module is optional. It is called only when a bearer token is available.
"""

from __future__ import annotations

from datetime import UTC, datetime

import requests

TWITTER_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


def fetch_recent_tweets(
    query: str, bearer_token: str, max_results: int = 25
) -> list[dict[str, str]]:
    """Fetch recent tweets using Twitter/X API v2 recent search.

    Parameters
    ----------
    query:
        Twitter/X recent-search query.
    bearer_token:
        API bearer token.
    max_results:
        Number of tweets to request. Twitter API minimum is usually 10.

    Returns
    -------
    list[dict[str, str]]
        Raw records compatible with the data pipeline.
    """

    params = {
        "query": query,
        "max_results": max(10, min(max_results, 100)),
        "tweet.fields": "created_at,author_id,lang",
    }
    response = requests.get(
        TWITTER_RECENT_SEARCH_URL,
        params=params,
        headers={"Authorization": f"Bearer {bearer_token}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = []
    for item in payload.get("data", []):
        rows.append(
            {
                "tweet_id": item.get("id"),
                "text": item.get("text", ""),
                "author": item.get("author_id", "unknown"),
                "created_at": item.get("created_at", datetime.now(UTC).isoformat()),
                "source": "twitter_recent_search",
            }
        )
    return rows
