"""End-to-end processing pipeline for raw social-media data."""

from __future__ import annotations

import pandas as pd

from .finbert import get_finbert_classifier
from .preprocessing import prepare_tweets
from .sentiment import add_sentiment as add_lexicon_sentiment
from .topics import add_topics


def process_tweets(
    df: pd.DataFrame,
    *,
    sentiment_model: str = "lexicon",
    finbert_model_name: str = "ProsusAI/finbert",
    finbert_batch_size: int = 16,
) -> pd.DataFrame:
    """Run the complete analytics pipeline.

    Parameters
    ----------
    df:
        Raw dataframe with at least a ``text`` column.
    sentiment_model:
        ``lexicon`` for the lightweight baseline, or ``finbert`` for transformer
        inference.
    finbert_model_name:
        Hugging Face FinBERT model id.
    finbert_batch_size:
        Batch size for CPU FinBERT inference.

    Returns
    -------
    pandas.DataFrame
        Processed dataframe with text, ticker, topic and sentiment columns.
    """

    prepared = prepare_tweets(df)

    if sentiment_model.strip().lower() == "finbert":
        classifier = get_finbert_classifier(finbert_model_name)
        scored = classifier.add_sentiment(
            prepared,
            text_column="clean_text",
            batch_size=finbert_batch_size,
        )
    else:
        scored = add_lexicon_sentiment(prepared)
        scored["sentiment_confidence"] = None
        scored["positive_prob"] = None
        scored["neutral_prob"] = None
        scored["negative_prob"] = None
        scored["sentiment_model"] = "lexicon"

    return add_topics(scored)
