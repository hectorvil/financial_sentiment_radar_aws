from datetime import UTC, datetime

from financial_sentiment.live_query_catalog import build_company_query, rotate_ticker


def test_build_company_query_uses_trusted_accounts_and_filters():
    query = build_company_query("NVDA", trusted_accounts_only=True)
    assert "from:Reuters" in query
    assert "NVDA" in query
    assert "-is:retweet" in query
    assert "lang:en" in query


def test_rotate_ticker_is_deterministic_for_window():
    tickers = ["NVDA", "TSLA", "AAPL"]
    now = datetime(2026, 5, 20, 10, 0, tzinfo=UTC)
    assert rotate_ticker(tickers, now=now) in tickers
