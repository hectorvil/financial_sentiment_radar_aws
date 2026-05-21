"""Small X API v2 client for controlled recent-search ingestion."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


class XApiError(RuntimeError):
    """Raised when X API returns an error response."""


def search_recent_posts(
    *,
    bearer_token: str,
    query: str,
    max_results: int = 10,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Call X API recent search.

    Args:
        bearer_token: X API bearer token.
        query: Search query using X operators.
        max_results: Maximum posts to return. X recent search supports 10 as a safe minimum.
        timeout_seconds: HTTP timeout.

    Returns:
        Raw JSON response from X API.
    """
    if not bearer_token:
        raise ValueError("bearer_token is required")

    safe_max = max(10, min(int(max_results), 100))

    params = {
        "query": query,
        "max_results": safe_max,
        "tweet.fields": "id,text,created_at,author_id,lang,public_metrics,source",
        "expansions": "author_id",
        "user.fields": "id,username,name,verified",
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}

    response = requests.get(
        RECENT_SEARCH_URL, headers=headers, params=params, timeout=timeout_seconds
    )

    if response.status_code >= 400:
        logger.error(
            "x_api_recent_search_failed status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise XApiError(f"X API error {response.status_code}: {response.text[:500]}")

    return response.json()


def flatten_recent_search_response(
    payload: dict[str, Any],
    *,
    query: str,
    query_ticker: str,
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
        rows.append(
            {
                "tweet_id": tweet.get("id"),
                "text": tweet.get("text", ""),
                "created_at": tweet.get("created_at"),
                "author_id": tweet.get("author_id"),
                "author_username": author.get("username"),
                "author_name": author.get("name"),
                "author_verified": author.get("verified"),
                "lang": tweet.get("lang"),
                "tweet_source": tweet.get("source"),
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
