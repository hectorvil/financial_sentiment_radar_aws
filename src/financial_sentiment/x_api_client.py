"""Small X API v2 client for controlled recent-search ingestion."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
MIN_USER_RESULTS = 3
MAX_INTERACTIVE_RESULTS = 25
X_API_MIN_RESULTS = 10


class XApiError(RuntimeError):
    """Raised when X API returns an error response."""


def normalize_max_results(max_results: int) -> int:
    """Clamp user-facing live-search results to 3-25.

    X's recent-search endpoint has an API minimum page size of 10, but the
    product UX can request as few as 3 tweets. The HTTP client fetches at least
    10 when needed, and the service trims the dataframe back to this value.
    """
    return max(MIN_USER_RESULTS, min(int(max_results), MAX_INTERACTIVE_RESULTS))


def _api_max_results(user_max_results: int) -> int:
    """Return a value valid for X API recent search."""
    return max(X_API_MIN_RESULTS, min(int(user_max_results), 100))


def search_recent_posts(
    *,
    bearer_token: str,
    query: str,
    max_results: int = 10,
    timeout_seconds: int = 20,
    sort_order: str | None = None,
) -> dict[str, Any]:
    """Call X API recent search.

    Args:
        bearer_token: X API bearer token.
        query: Search query using X operators.
        max_results: User-facing number of posts, typically 3-25.
        timeout_seconds: HTTP timeout.
        sort_order: Optional X sort order. Use ``recency`` for most current or
            ``relevancy`` when your API access supports it.

    Returns:
        Raw JSON response from X API.
    """
    if not bearer_token:
        raise ValueError("bearer_token is required")

    api_max = _api_max_results(max_results)

    params = {
        "query": query,
        "max_results": api_max,
        "tweet.fields": "id,text,created_at,author_id,lang,public_metrics,source,possibly_sensitive",
        "expansions": "author_id",
        "user.fields": "id,username,name,verified,description,public_metrics",
    }
    if sort_order in {"recency", "relevancy"}:
        params["sort_order"] = sort_order

    headers = {"Authorization": f"Bearer {bearer_token}"}
    response = requests.get(
        RECENT_SEARCH_URL, headers=headers, params=params, timeout=timeout_seconds
    )

    if response.status_code >= 400:
        logger.error(
            "x_api_recent_search_failed status=%s body=%s query=%s",
            response.status_code,
            response.text[:800],
            query[:500],
        )
        raise XApiError(f"X API error {response.status_code}: {response.text[:800]}")

    return response.json()


def flatten_recent_search_response(
    payload: dict[str, Any],
    *,
    query: str,
    query_ticker: str | None,
    query_name: str,
) -> list[dict[str, Any]]:
    """Flatten X API recent-search response into dataframe-ready rows."""
    users = {
        user.get("id"): user
        for user in payload.get("includes", {}).get("users", [])
        if user.get("id")
    }

    rows: list[dict[str, Any]] = []
    for tweet in payload.get("data", []) or []:
        author = users.get(tweet.get("author_id"), {})
        metrics = tweet.get("public_metrics", {}) or {}
        author_metrics = author.get("public_metrics", {}) or {}
        rows.append(
            {
                "tweet_id": tweet.get("id"),
                "text": tweet.get("text", ""),
                "created_at": tweet.get("created_at"),
                "author_id": tweet.get("author_id"),
                "author_username": author.get("username"),
                "author_name": author.get("name"),
                "author_verified": author.get("verified"),
                "author_description": author.get("description"),
                "author_followers": author_metrics.get("followers_count"),
                "lang": tweet.get("lang"),
                "tweet_source": tweet.get("source"),
                "possibly_sensitive": tweet.get("possibly_sensitive"),
                "retweet_count": metrics.get("retweet_count"),
                "reply_count": metrics.get("reply_count"),
                "like_count": metrics.get("like_count"),
                "quote_count": metrics.get("quote_count"),
                "query": query,
                "query_ticker": query_ticker,
                "query_name": query_name,
                "source": "twitter_live",
            }
        )

    return rows
