"""FinBERT sentiment classification utilities.

FinBERT is optional. The default app still uses the lightweight lexicon model
unless ``SENTIMENT_MODEL=finbert`` is configured. The imports for transformers
and torch are lazy so tests and lexicon-only deployments do not download or load
large models.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pandas as pd

DEFAULT_FINBERT_MODEL = "ProsusAI/finbert"


@dataclass(frozen=True)
class FinBertPrediction:
    """Prediction returned by FinBERT for one text."""

    sentiment: str
    sentiment_confidence: float
    positive_prob: float
    neutral_prob: float
    negative_prob: float


def _load_transformer_dependencies() -> tuple[Any, Any, Any]:
    """Load torch and transformers lazily.

    Returns
    -------
    tuple
        ``(torch, AutoTokenizer, AutoModelForSequenceClassification)``.
    """

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    return torch, AutoTokenizer, AutoModelForSequenceClassification


class FinBertClassifier:
    """CPU FinBERT classifier for batch inference.

    Parameters
    ----------
    model_name:
        Hugging Face model id. Defaults to ``ProsusAI/finbert``.
    tokenizer, model, torch_module:
        Optional injected dependencies used by tests to avoid downloading the
        real model.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_FINBERT_MODEL,
        *,
        tokenizer: Any | None = None,
        model: Any | None = None,
        torch_module: Any | None = None,
    ) -> None:
        """Implements the `__init__` step used by this module.

        Args:
            model_name: Input value consumed by this function.
            tokenizer: Input value consumed by this function.
            model: Input value consumed by this function.
            torch_module: Input value consumed by this function.

        Returns:
            None: Result produced by the function.
        """
        self.model_name = model_name

        if tokenizer is None or model is None or torch_module is None:
            torch_module, auto_tokenizer, auto_model = _load_transformer_dependencies()
            tokenizer = tokenizer or auto_tokenizer.from_pretrained(model_name)
            model = model or auto_model.from_pretrained(model_name)

        self.torch = torch_module
        self.tokenizer = tokenizer
        self.model = model
        self.model.eval()
        self.id_to_label = getattr(
            self.model.config, "id2label", {0: "negative", 1: "neutral", 2: "positive"}
        )

    def predict_texts(
        self,
        texts: list[str],
        *,
        batch_size: int = 16,
        max_length: int = 128,
    ) -> list[FinBertPrediction]:
        """Classify texts as positive, neutral or negative."""

        clean_texts = [str(text or "").strip() for text in texts]
        predictions: list[FinBertPrediction] = []

        for start in range(0, len(clean_texts), batch_size):
            batch_texts = clean_texts[start : start + batch_size]
            encoded = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )

            with self.torch.no_grad():
                outputs = self.model(**encoded)
                probabilities = self.torch.softmax(outputs.logits, dim=1)

            for probs in probabilities:
                best_index = int(self.torch.argmax(probs).item())
                raw_label = str(self.id_to_label.get(best_index, best_index)).lower()
                prob_list = [float(value) for value in probs.tolist()]
                prob_by_label = {
                    str(self.id_to_label.get(index, index)).lower(): prob
                    for index, prob in enumerate(prob_list)
                }

                predictions.append(
                    FinBertPrediction(
                        sentiment=raw_label,
                        sentiment_confidence=float(prob_list[best_index]),
                        positive_prob=float(prob_by_label.get("positive", 0.0)),
                        neutral_prob=float(prob_by_label.get("neutral", 0.0)),
                        negative_prob=float(prob_by_label.get("negative", 0.0)),
                    )
                )

        return predictions

    def add_sentiment(
        self,
        df: pd.DataFrame,
        *,
        text_column: str = "clean_text",
        batch_size: int = 16,
        max_length: int = 128,
    ) -> pd.DataFrame:
        """Add FinBERT sentiment columns to a dataframe."""

        if text_column not in df.columns:
            raise ValueError(f"Dataframe must include a '{text_column}' column.")

        output = df.copy()
        texts = output[text_column].fillna("").astype(str).tolist()
        predictions = self.predict_texts(texts, batch_size=batch_size, max_length=max_length)

        output["sentiment"] = [prediction.sentiment for prediction in predictions]
        output["sentiment_confidence"] = [
            prediction.sentiment_confidence for prediction in predictions
        ]
        output["positive_prob"] = [prediction.positive_prob for prediction in predictions]
        output["neutral_prob"] = [prediction.neutral_prob for prediction in predictions]
        output["negative_prob"] = [prediction.negative_prob for prediction in predictions]
        output["sentiment_score"] = output["positive_prob"] - output["negative_prob"]
        output["sentiment_model"] = self.model_name
        return output


@lru_cache(maxsize=2)
def get_finbert_classifier(model_name: str = DEFAULT_FINBERT_MODEL) -> FinBertClassifier:
    """Return a cached classifier so Streamlit does not reload it on every rerun."""

    return FinBertClassifier(model_name=model_name)
