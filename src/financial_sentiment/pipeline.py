"""End-to-end processing pipeline for raw social-media data."""

from __future__ import annotations

import pandas as pd

from .preprocessing import prepare_tweets
from .sentiment import add_sentiment
from .topics import add_topics


def process_tweets(df: pd.DataFrame) -> pd.DataFrame:
    """Run the complete lightweight analytics pipeline.

    Parameters
    ----------
    df:
        Raw dataframe with at least a ``text`` column.

    Returns
    -------
    pandas.DataFrame
        Processed dataframe with text, ticker, topic and sentiment columns.
    """

    prepared = prepare_tweets(df)
    scored = add_sentiment(prepared)
    return add_topics(scored)
