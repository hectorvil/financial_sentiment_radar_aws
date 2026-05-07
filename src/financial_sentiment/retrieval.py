"""Simple retrieval layer for product questions."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class SearchResult:
    """Retrieved evidence row."""

    doc_id: str
    text: str
    score: float
    sentiment: str
    tickers: str
    topic: str


class TweetRetriever:
    """TF-IDF based retriever for short financial texts.

    The class is intentionally local and deterministic so the app can answer
    questions even when Bedrock is disabled.
    """

    def __init__(self, df: pd.DataFrame):
        """Create a retriever from a processed dataframe."""

        self.df = df.reset_index(drop=True).copy()
        self.vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), max_features=5000
        )
        if self.df.empty:
            self.matrix = None
            return

        try:
            self.matrix = self.vectorizer.fit_transform(self.df["clean_text"].astype(str))
        except ValueError:
            # This can happen when all documents are empty after tokenization or
            # contain only stop words. The app should degrade gracefully instead
            # of breaking the user experience.
            self.matrix = None

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """Return the top-k documents for a user query.

        Parameters
        ----------
        query:
            Natural-language question or keywords.
        k:
            Maximum number of evidence rows.

        Returns
        -------
        list[SearchResult]
            Evidence rows ordered by semantic similarity.
        """

        if self.df.empty or self.matrix is None or not query.strip():
            return []

        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix).ravel()
        top_positions = scores.argsort()[::-1][:k]

        results: list[SearchResult] = []
        for pos in top_positions:
            row = self.df.iloc[pos]
            if scores[pos] <= 0:
                continue
            tickers = row.get("tickers", [])
            tickers_display = ", ".join(tickers) if isinstance(tickers, list) else str(tickers)
            results.append(
                SearchResult(
                    doc_id=str(row.get("doc_id", "")),
                    text=str(row.get("clean_text", "")),
                    score=round(float(scores[pos]), 4),
                    sentiment=str(row.get("sentiment", "neutral")),
                    tickers=tickers_display,
                    topic=str(row.get("topic", "general_market")),
                )
            )
        return results


def build_extractive_answer(query: str, results: list[SearchResult]) -> str:
    """Generate a deterministic answer when LLM summarization is disabled.

    Parameters
    ----------
    query:
        User question.
    results:
        Retrieved evidence.

    Returns
    -------
    str
        Concise Spanish summary grounded in the retrieved rows.
    """

    if not results:
        return "No encontré evidencia suficiente en el corpus cargado para responder esa pregunta."

    sentiment_counts = pd.Series([result.sentiment for result in results]).value_counts().to_dict()
    dominant = max(sentiment_counts, key=sentiment_counts.get)
    sample = "\n".join(f"- {result.text[:220]}" for result in results[:5])
    return (
        f"Para la consulta '{query}', recuperé {len(results)} textos relacionados. "
        f"El tono dominante en la evidencia es '{dominant}'.\n\n"
        f"Evidencia principal:\n{sample}\n\n"
        "Interpretación: usa esta señal como radar temprano de percepción, no como recomendación de inversión."
    )
