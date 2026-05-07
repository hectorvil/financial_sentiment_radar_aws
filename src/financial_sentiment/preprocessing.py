"""Preprocessing functions for financial social-media text.

The module is intentionally lightweight so it can run on small Fargate tasks.
It handles text cleanup, ticker/company extraction and normalizes expected
columns before analytics or retrieval.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

import pandas as pd

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\w+")
SPACE_PATTERN = re.compile(r"\s+")
CASHTAG_PATTERN = re.compile(r"\$([A-Z]{1,6})(?![A-Z])")

# Keep the mapping small and explicit for an MVP. Add more aliases when the
# product scope expands.
COMPANY_ALIASES: dict[str, list[str]] = {
    "AAPL": ["apple", "$aapl", "iphone"],
    "AMZN": ["amazon", "$amzn", "aws"],
    "BBVA": ["bbva", "$bbva"],
    "GOOGL": ["alphabet", "google", "$googl"],
    "JPM": ["jpmorgan", "jp morgan", "$jpm"],
    "MSFT": ["microsoft", "$msft", "azure"],
    "NVDA": ["nvidia", "$nvda", "gpu"],
    "TSLA": ["tesla", "$tsla", "elon"],
}

TICKER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(ticker) for ticker in COMPANY_ALIASES) + r")\b",
    flags=re.IGNORECASE,
)


def clean_text(text: object) -> str:
    """Normalize tweet text for analytics and retrieval.

    Parameters
    ----------
    text:
        Raw tweet or social-media text.

    Returns
    -------
    str
        Cleaned text with URLs, mentions and duplicated whitespace removed.
    """

    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    value = str(text)
    value = URL_PATTERN.sub(" ", value)
    value = MENTION_PATTERN.sub(" ", value)
    value = value.replace("\n", " ").strip()
    return SPACE_PATTERN.sub(" ", value)


def extract_tickers(text: str) -> list[str]:
    """Extract supported company tickers from text.

    Parameters
    ----------
    text:
        Cleaned or raw text.

    Returns
    -------
    list[str]
        Sorted unique tickers detected in the text.
    """

    lower_text = text.lower()
    tickers: set[str] = set()

    for ticker in CASHTAG_PATTERN.findall(text.upper()):
        if ticker in COMPANY_ALIASES:
            tickers.add(ticker)

    for match in TICKER_PATTERN.findall(text):
        tickers.add(match.upper())

    for ticker, aliases in COMPANY_ALIASES.items():
        if any(alias in lower_text for alias in aliases):
            tickers.add(ticker)

    return sorted(tickers)


def normalize_created_at(values: Iterable[object]) -> pd.Series:
    """Parse timestamps and fill missing values with the current UTC time.

    Parameters
    ----------
    values:
        Iterable with timestamp-like values.

    Returns
    -------
    pandas.Series
        Timezone-naive UTC timestamps for plotting compatibility.
    """

    parsed = pd.to_datetime(pd.Series(values), errors="coerce", utc=True)
    fallback = pd.Timestamp(datetime.now(UTC))
    parsed = parsed.fillna(fallback)
    return parsed.dt.tz_convert(None)


def prepare_tweets(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare a raw tweet dataframe for scoring.

    Required input column is ``text``. Optional columns include ``tweet_id``,
    ``created_at``, ``author`` and ``source``.

    Parameters
    ----------
    df:
        Raw tweets dataframe.

    Returns
    -------
    pandas.DataFrame
        Normalized dataframe with clean text, tickers and timestamps.
    """

    if "text" not in df.columns:
        raise ValueError("Input data must include a 'text' column.")

    prepared = df.copy()
    prepared["text"] = prepared["text"].fillna("").astype(str)
    prepared["clean_text"] = prepared["text"].map(clean_text)
    prepared = prepared[prepared["clean_text"].str.len() > 0].copy()

    if "tweet_id" not in prepared.columns:
        prepared["tweet_id"] = [f"local-{i}" for i in range(len(prepared))]

    if "created_at" not in prepared.columns:
        prepared["created_at"] = datetime.now(UTC).isoformat()

    if "author" not in prepared.columns:
        prepared["author"] = "unknown"

    if "source" not in prepared.columns:
        prepared["source"] = "manual_or_sample"

    prepared["created_at"] = normalize_created_at(prepared["created_at"])
    prepared["tickers"] = prepared["clean_text"].map(extract_tickers)
    prepared["primary_ticker"] = prepared["tickers"].map(
        lambda values: values[0] if values else "UNMAPPED"
    )
    prepared["doc_id"] = prepared["tweet_id"].astype(str)
    prepared = prepared.drop_duplicates(subset=["doc_id"]).reset_index(drop=True)
    return prepared
