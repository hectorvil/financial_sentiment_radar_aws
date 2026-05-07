import re
import emoji
from pathlib import Path
import pandas as pd
import torch
import joblib
import streamlit as st
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ── tablas de mapeo ───────────────────────────────────────────────
id2label = {0: "negative", 1: "neutral", 2: "positive"}

label_map = [
    "Analyst Update", "Bank", "Buyback", "Dividend", "ECB", "Federal Reserve",
    "Financials", "Forecast", "General News", "Gold", "IPO", "Market Commentary",
    "Mergers & Acquisitions", "Oil", "Politics", "Quarterly Results",
    "Stock Movement", "Tech", "Trade", "USD"
]

# ── carga de clasificador de temas ────────────────────────────────
topic_path = Path(__file__).with_name("topic_clf.joblib")
topic_clf = joblib.load(topic_path) if topic_path.exists() else None

# ── FinBERT cacheado ──────────────────────────────────────────────
@st.cache_resource
def load_finbert():
    tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    mdl = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    mdl.eval()
    return tok, mdl

# ── utilidades de limpieza ───────────────────────────────────────
def clean(text: str) -> str:
    text = emoji.replace_emoji(text, replace="")
    text = re.sub(r"http\S+|@\w+|#\w+", "", text)
    return re.sub(r"\s+", " ", text).strip()

def finbert_sentiment(texts: list[str], batch: int = 16) -> list[str]:
    """
    Devuelve ['positive'|'neutral'|'negative'] usando SIEMPRE CPU.
    Evita cualquier riesgo de CUDA illegal memory access.
    """
    tokenizer, model = load_finbert()   # el modelo está en CPU por defecto
    preds: list[int] = []

    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        toks = tokenizer(chunk, padding=True, truncation=True, return_tensors="pt")  # tensors en CPU
        with torch.inference_mode():
            logits = model(**toks).logits          # forward en CPU
        preds.extend(torch.argmax(logits, dim=1).tolist())

    return [id2label[p] for p in preds]


COMMON_WORDS = {
    "BANK", "GDP", "FED", "ECB",
    "AND", "THE", "YEAR", "TIME", "NEWS", "DATA"
}

def extract_tickers(text: str) -> list[str]:
    """Devuelve lista de símbolos de 2-5 letras en mayúsculas que no sean stop-words."""
    tickers = [t.lstrip("$") for t in re.findall(r"\$?[A-Z]{2,5}\b", text)]
    return [t for t in tickers if t not in COMMON_WORDS]


# ── pipeline principal ───────────────────────────────────────────
def add_labels(df: pd.DataFrame, *, skip_if_present: bool = True) -> pd.DataFrame:
    """
    Añade columnas clean, sentiment, tickers y topic solo si faltan.
    Si `skip_if_present=True`, respeta las columnas ya calculadas.
    """
    df = df.copy()

    # Clean
    if "clean" not in df:
        df["clean"] = df["text"].map(clean)

    # Sentiment
    if "sentiment" not in df:
        df["sentiment"] = finbert_sentiment(df["clean"].tolist())

    # Tickers
    if "tickers" not in df or not skip_if_present:
        df["tickers"] = df["clean"].map(extract_tickers)

    # Topic
    if "topic" not in df:
        if "label" in df:
            df["topic"] = df["label"].map(
                lambda x: label_map[x] if 0 <= x < len(label_map) else "Unknown"
            )
        elif topic_clf:
            df["topic"] = topic_clf.predict(df["clean"])
        else:
            df["topic"] = "Unknown"

    return df
