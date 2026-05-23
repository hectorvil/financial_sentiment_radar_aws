"""Local ranking for live X/Twitter search candidates.

The ranking layer combines public engagement metrics, trusted-source bonuses,
financial-keyword signals, and noise penalties. It is used after X returns
candidates and before Bedrock/FinBERT spend additional compute."""

from __future__ import annotations

import math

import pandas as pd

FINANCIAL_STRONG_TERMS = {
    "moody",
    "moody's",
    "moody’s",
    "moodys",
    "fitch",
    "s&p",
    "rating",
    "downgrade",
    "upgrade",
    "baa3",
    "baa2",
    "calificación",
    "calificacion",
    "deuda soberana",
    "grado de inversión",
    "grado de inversion",
    "nota soberana",
    "credit rating",
    "sovereign",
    "banxico",
    "fed",
    "inflación",
    "inflacion",
    "tasa",
    "tasas",
    "interest rate",
    "central bank",
    "monetary policy",
    "earnings",
    "revenue",
    "guidance",
    "profit",
    "margin",
    "stock",
    "shares",
    "market",
    "markets",
    "acciones",
    "bonos",
    "antitrust",
    "regulation",
    "lawsuit",
    "doj",
    "sec",
    "oil",
    "brent",
    "wti",
    "dollar",
    "peso",
    "fx",
    "forex",
    "debt",
    "bond",
    "bonds",
    "spread",
    "risk",
    "credit",
}

NOISE_TERMS = {
    "giveaway",
    "airdrop",
    "free crypto",
    "casino",
    "betting",
    "onlyfans",
    "meme coin",
    "promo code",
    "sorteo",
    "apuesta",
    "porn",
    "nsfw",
    "trading bot",
    "pump",
    "100x",
}

BROAD_NON_FINANCIAL_TERMS = {
    "random political",
    "political noise",
    "fútbol",
    "futbol",
    "football",
    "celebrity",
    "gossip",
    "meme",
    "viral joke",
}


def candidate_pool_size(requested: int) -> int:
    """Fetch a small candidate pool to control X API cost.

    Conservative strategy:
    - User asks 3-5 tweets  -> fetch 10 candidates
    - User asks 6-10 tweets -> fetch 15 candidates
    - User asks 11-25       -> fetch 20 candidates

    The goal is precision first, not broad expensive search.
    """
    requested = max(3, min(int(requested), 25))

    if requested <= 5:
        return 10
    if requested <= 10:
        return 15

    return 20


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Implements the `_num` step used by this module.

    Args:
        df: Input value consumed by this function.
        col: Input value consumed by this function.

    Returns:
        pd.Series: Result produced by the function.
    """
    if col not in df.columns:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def _contains_any(text: str, terms: set[str]) -> bool:
    """Implements the `_contains_any` step used by this module.

    Args:
        text: Input value consumed by this function.
        terms: Input value consumed by this function.

    Returns:
        bool: Result produced by the function.
    """
    lower = str(text).lower()
    return any(term in lower for term in terms)


def add_engagement_ranking(
    df: pd.DataFrame,
    *,
    curated_accounts: set[str] | None = None,
) -> pd.DataFrame:
    """Rank X candidates locally.

    Engagement helps, but it should not dominate if the tweet has no financial signal.
    The ranking gives priority to:
    1. Financial relevance.
    2. Curated source.
    3. Engagement, using log scale.
    4. Noise penalties.
    """
    if df.empty:
        return df

    out = df.copy()
    curated = {a.lower().replace("@", "") for a in (curated_accounts or set())}

    raw_engagement = (
        _num(out, "like_count")
        + 2.0 * _num(out, "retweet_count")
        + 2.0 * _num(out, "quote_count")
        + 1.0 * _num(out, "reply_count")
        + 0.2 * _num(out, "bookmark_count")
    )
    out["engagement_score"] = raw_engagement

    # Log scale: a tweet with 500 likes should help, but not beat relevance by itself.
    out["engagement_rank_score"] = raw_engagement.map(lambda x: 6.0 * math.log1p(float(x)))

    if "author_username" in out.columns:
        authors = out["author_username"].fillna("").astype(str).str.lower().str.replace("@", "")
        out["source_score"] = authors.map(lambda x: 25.0 if x in curated else 0.0)
    else:
        out["source_score"] = 0.0

    if "text" in out.columns:
        texts = out["text"].fillna("").astype(str)
        has_finance = texts.map(lambda x: _contains_any(x, FINANCIAL_STRONG_TERMS))
        has_noise = texts.map(
            lambda x: _contains_any(x, NOISE_TERMS) or _contains_any(x, BROAD_NON_FINANCIAL_TERMS)
        )

        out["finance_relevance_score"] = has_finance.map(lambda x: 45.0 if x else 0.0)
        out["noise_penalty"] = has_noise.map(lambda x: -120.0 if x else 0.0)

        # If a tweet is neither financial nor from a curated account, penalize it hard.
        # This avoids viral but irrelevant tweets dominating.
        out["off_topic_penalty"] = [
            0.0 if finance or source > 0 else -80.0
            for finance, source in zip(has_finance, out["source_score"], strict=False)
        ]
    else:
        out["finance_relevance_score"] = 0.0
        out["noise_penalty"] = 0.0
        out["off_topic_penalty"] = -80.0

    out["ranking_score"] = (
        out["finance_relevance_score"]
        + out["source_score"]
        + out["engagement_rank_score"]
        + out["noise_penalty"]
        + out["off_topic_penalty"]
    )

    return out.sort_values("ranking_score", ascending=False).reset_index(drop=True)
