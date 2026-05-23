"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from __future__ import annotations

import pandas as pd

from financial_sentiment.schema_inference import infer_schema, infer_schema_with_rules


def test_schema_inference_detects_text_column() -> None:
    """Implements the `test_schema_inference_detects_text_column` step used by this module.

    Returns:
        None: Result produced by the function.
    """
    df = pd.DataFrame(
        {
            "text": [
                "$TSLA shares fall after weak delivery guidance",
                "$NVDA rallies on strong AI chip demand",
            ],
            "label": [0, 1],
        }
    )

    mapping = infer_schema_with_rules(df)

    assert mapping.tweet_text_column == "text"
    assert mapping.method == "rules"
    assert mapping.confidence >= 0.8
    assert mapping.label_column == "label"


def test_schema_inference_avoids_label_column() -> None:
    """Implements the `test_schema_inference_avoids_label_column` step used by this module.

    Returns:
        None: Result produced by the function.
    """
    df = pd.DataFrame(
        {
            "label": [0, 1, 2],
            "content": [
                "Google shares move higher after cloud revenue beats expectations",
                "Tesla stock drops as margins disappoint investors",
                "BBVA earnings remain stable despite rate volatility",
            ],
        }
    )

    mapping = infer_schema_with_rules(df)

    assert mapping.tweet_text_column == "content"
    assert mapping.label_column == "label"


def test_schema_inference_ambiguous_returns_needs_bedrock() -> None:
    """Implements the `test_schema_inference_ambiguous_returns_needs_bedrock` step used by this module.

    Returns:
        None: Result produced by the function.
    """
    df = pd.DataFrame(
        {
            "alpha": [
                "Markets discuss chip demand and AI revenue growth for Nvidia",
                "Investors debate margins and delivery risk for Tesla",
            ],
            "beta": [
                "Analysts mention stock volatility and earnings uncertainty",
                "Traders watch guidance and revenue after the rally",
            ],
        }
    )

    mapping = infer_schema(df, use_bedrock=False)

    assert mapping.tweet_text_column is None
    assert mapping.method == "needs_bedrock"
