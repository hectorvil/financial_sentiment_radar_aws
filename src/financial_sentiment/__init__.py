"""Financial Sentiment Radar package.

This package contains the reusable modules for the data product:
- ingestion and storage
- text preprocessing
- sentiment and topic scoring
- retrieval for user questions
- optional Amazon Bedrock summarization
"""

from .config import AppConfig
from .preprocessing import prepare_tweets
from .sentiment import score_sentiment

__all__ = ["AppConfig", "prepare_tweets", "score_sentiment"]
