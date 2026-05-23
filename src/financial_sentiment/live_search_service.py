"""Interactive live X/Twitter search service for the Consultas tab.

This final version separates live search into two UX steps:

1. Preview: search X, label noise/relevance, classify relevant tweets, and show
   both noisy and relevant posts to the user.
2. Ingest: only after user confirmation, persist relevant tweets into S3
   bronze/silver/gold and update ``gold/twitter_live/latest.parquet``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from financial_sentiment.live_query_catalog import (
    CURATED_MARKET_ACCOUNT_UNIVERSE,
    build_loose_fallback_query,
    build_reliable_broad_query,
    classify_author_reliability,
    is_curated_market_author,
)
from financial_sentiment.live_ranking import add_engagement_ranking, candidate_pool_size
from financial_sentiment.live_relevance import (
    apply_relevance_labels,
    get_relevance_labels,
    summarize_live_tweets,
)
from financial_sentiment.medallion import (
    make_run_id,
    silverize_tweets,
    update_live_latest,
    write_medallion_datasets,
    write_twitter_bronze,
)
from financial_sentiment.multilingual_finbert import process_tweets_with_optional_translation
from financial_sentiment.query_anchor_filter import build_precise_anchor_query
from financial_sentiment.x_api_client import (
    flatten_recent_search_response,
    normalize_max_results,
    search_recent_posts,
)

logger = logging.getLogger(__name__)


@dataclass
class LiveSearchPreview:
    """Preview generated before S3 ingestion."""

    rows_requested: int
    rows_raw: int
    rows_relevant: int
    query: str
    run_id: str
    summary: str
    bronze_payload: dict[str, Any]
    raw_df: pd.DataFrame
    relevant_df: pd.DataFrame
    warning: str | None = None


@dataclass(frozen=True)
class DirectLiveSearchResult:
    """Result after confirmed ingestion."""

    rows_requested: int
    rows_raw: int
    rows_relevant: int
    query: str
    run_id: str
    summary: str
    bronze_uri: str | None
    silver_uri: str | None
    gold_uri: str | None
    latest_uri: str | None
    raw_df: pd.DataFrame
    relevant_df: pd.DataFrame


def _search_with_fallback(
    *,
    bearer_token: str,
    query: str,
    max_results: int,
    sort_order: str,
) -> dict[str, Any]:
    """Search X and retry with recency if relevancy is unsupported."""
    try:
        return search_recent_posts(
            bearer_token=bearer_token,
            query=query,
            max_results=max_results,
            sort_order=sort_order,
        )
    except Exception as exc:
        if sort_order == "relevancy":
            logger.warning(
                "x_relevancy_sort_failed_retry_recency error_type=%s", type(exc).__name__
            )
            return search_recent_posts(
                bearer_token=bearer_token,
                query=query,
                max_results=max_results,
                sort_order="recency",
            )
        raise


def _allocation(max_results: int, search_scope: str) -> tuple[int, int]:
    """Allocate result cap between broad and curated passes."""
    if search_scope != "broad_all_x" or max_results < 20:
        return max_results, 0
    return max_results - 10, 10


def _combine_payloads(
    payloads: list[dict[str, Any]], queries: list[str], user_query: str
) -> dict[str, Any]:
    """Return bronze payload preserving all X responses."""
    return {
        "user_query": user_query,
        "queries": queries,
        "responses": payloads,
        "strategy": "preview_then_confirm_ingest_broad_x_plus_curated_trader_sources",
    }


def _flatten_payloads(
    *,
    payloads: list[dict[str, Any]],
    queries: list[str],
    inferred_ticker: str | None,
    inferred_name: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    """Flatten, annotate, deduplicate and trim X API responses."""
    rows: list[dict[str, Any]] = []
    for payload, query in zip(payloads, queries, strict=False):
        rows.extend(
            flatten_recent_search_response(
                payload,
                query=query,
                query_ticker=inferred_ticker,
                query_name=inferred_name,
            )
        )

    if not rows:
        return []

    df = pd.DataFrame(rows)
    if "tweet_id" in df.columns:
        df = df.drop_duplicates(subset=["tweet_id"], keep="first")
    elif "text" in df.columns:
        df = df.drop_duplicates(subset=["text"], keep="first")

    if "author_username" in df.columns:
        df["author_reliability_tier"] = df["author_username"].map(classify_author_reliability)
        df["is_curated_market_author"] = df["author_username"].map(is_curated_market_author)

    for col in ["like_count", "retweet_count", "reply_count", "quote_count"]:
        if col not in df.columns:
            df[col] = 0
    df["_curated_boost"] = df.get("is_curated_market_author", False).fillna(False).astype(int)
    df["_engagement"] = (
        df["like_count"].fillna(0)
        + df["retweet_count"].fillna(0)
        + df["reply_count"].fillna(0)
        + df["quote_count"].fillna(0)
    )
    df = df.sort_values(["_curated_boost", "_engagement"], ascending=False)
    df = df.drop(columns=["_curated_boost", "_engagement"])
    return df.head(max_rows).to_dict("records")


def _run_x_queries(
    *,
    user_query: str,
    bearer_token: str,
    max_results: int,
    language: str,
    sort_order: str,
    max_accounts: int,
    search_scope: str,
) -> tuple[list[dict[str, Any]], list[str], str | None, str, str | None]:
    """Execute primary X query and broaden if no rows are returned."""
    precise_anchor_query = build_precise_anchor_query(user_query, language=language)
    if precise_anchor_query:
        queries = [precise_anchor_query]
        payloads = [
            _search_with_fallback(
                bearer_token=bearer_token,
                query=precise_anchor_query,
                max_results=max_results,
                sort_order=sort_order,
            )
        ]

        rows = _flatten_payloads(
            payloads=payloads,
            queries=queries,
            inferred_ticker=None,
            inferred_name="Precise anchored financial query",
            max_rows=max_results,
        )

        warning = (
            "Se usó una búsqueda precisa por entidades financieras clave. "
            "No se hizo fallback amplio automático para controlar costo y ruido."
        )

        if not rows:
            warning = (
                "No encontré tweets que conservaran las entidades clave de tu consulta. "
                "Puedes intentar con más resultados, recency o una frase menos restrictiva."
            )

        return payloads, queries, None, "Precise anchored financial query", warning

    broad_limit, curated_limit = _allocation(max_results, search_scope)
    primary_scope = "curated_accounts" if search_scope == "curated_accounts" else "broad_all_x"

    primary_query, inferred_ticker, inferred_name = build_reliable_broad_query(
        user_query,
        language=language,
        max_accounts=max_accounts,
        search_scope=primary_scope,
    )

    queries = [primary_query]
    payloads = [
        _search_with_fallback(
            bearer_token=bearer_token,
            query=primary_query,
            max_results=broad_limit,
            sort_order=sort_order,
        )
    ]

    rows = _flatten_payloads(
        payloads=payloads,
        queries=queries,
        inferred_ticker=inferred_ticker,
        inferred_name=inferred_name,
        max_rows=max_results,
    )

    warning: str | None = None
    low_coverage_threshold = min(max_results, max(10, max_results // 2))

    if len(rows) < low_coverage_threshold:
        fallback_query = build_loose_fallback_query(user_query, language=language)

        if not rows:
            warning = "La primera query no regresó resultados; se reintentó con una query menos restrictiva."
        else:
            warning = (
                f"La primera query regresó pocos candidatos ({len(rows)}); "
                "se agregó una búsqueda más amplia para mejorar cobertura."
            )

        if fallback_query not in queries:
            queries.append(fallback_query)
            payloads.append(
                _search_with_fallback(
                    bearer_token=bearer_token,
                    query=fallback_query,
                    max_results=max_results,
                    sort_order="recency",
                )
            )

    if curated_limit:
        curated_query, curated_ticker, curated_name = build_reliable_broad_query(
            user_query,
            language=language,
            max_accounts=max_accounts,
            search_scope="curated_accounts",
        )
        inferred_ticker = inferred_ticker or curated_ticker
        inferred_name = inferred_name or curated_name
        queries.append(curated_query)
        payloads.append(
            _search_with_fallback(
                bearer_token=bearer_token,
                query=curated_query,
                max_results=curated_limit,
                sort_order=sort_order,
            )
        )

    return payloads, queries, inferred_ticker, inferred_name, warning


def preview_direct_live_search(
    *,
    user_query: str,
    bearer_token: str,
    region_name: str,
    max_results: int,
    sentiment_model: str,
    finbert_model_name: str,
    finbert_batch_size: int,
    use_bedrock: bool,
    bedrock_model_id: str,
    language: str = "auto",
    sort_order: str = "relevancy",
    max_accounts: int = 8,
    search_scope: str = "broad_all_x",
) -> LiveSearchPreview:
    """Search, label and classify live tweets without writing to S3."""
    safe_max = normalize_max_results(max_results)
    requested_results = safe_max
    candidate_results = candidate_pool_size(safe_max)

    run_id = make_run_id("twitter_consultas_live")

    payloads, queries, inferred_ticker, inferred_name, warning = _run_x_queries(
        user_query=user_query,
        bearer_token=bearer_token,
        max_results=candidate_results,
        language=language,
        sort_order=sort_order,
        max_accounts=max_accounts,
        search_scope=search_scope,
    )
    combined_query_for_display = "\n--- retry/curated pass ---\n".join(queries)
    bronze_payload = _combine_payloads(payloads, queries, user_query)

    rows = _flatten_payloads(
        payloads=payloads,
        queries=queries,
        inferred_ticker=inferred_ticker,
        inferred_name=inferred_name,
        max_rows=candidate_results,
    )
    raw_df = pd.DataFrame(rows)
    raw_df = add_engagement_ranking(
        raw_df,
        curated_accounts=set(CURATED_MARKET_ACCOUNT_UNIVERSE),
    )
    raw_df = raw_df.head(candidate_results).reset_index(drop=True)
    rows = raw_df.to_dict("records")

    logger.info(
        "direct_live_preview run_id=%s requested=%s raw_rows=%s use_bedrock=%s",
        run_id,
        safe_max,
        len(raw_df),
        use_bedrock,
    )

    if raw_df.empty:
        return LiveSearchPreview(
            rows_requested=safe_max,
            rows_raw=0,
            rows_relevant=0,
            query=combined_query_for_display,
            run_id=run_id,
            summary="No encontré tweets para esta búsqueda. Prueba con horizonte amplio, recency u otra frase.",
            bronze_payload=bronze_payload,
            raw_df=raw_df,
            relevant_df=raw_df,
            warning=warning,
        )

    labels = get_relevance_labels(
        rows,
        user_query=user_query,
        use_bedrock=use_bedrock,
        model_id=bedrock_model_id,
        region_name=region_name,
    )
    labeled = apply_relevance_labels(raw_df, labels)
    relevant_raw = labeled[~labeled["is_noise"].fillna(True)].copy()

    if relevant_raw.empty:
        summary = summarize_live_tweets(
            relevant_raw,
            user_query=user_query,
            use_bedrock=False,
            model_id=bedrock_model_id,
            region_name=region_name,
        )
        return LiveSearchPreview(
            rows_requested=safe_max,
            rows_raw=len(labeled),
            rows_relevant=0,
            query=combined_query_for_display,
            run_id=run_id,
            summary=summary,
            bronze_payload=bronze_payload,
            raw_df=labeled,
            relevant_df=relevant_raw,
            warning=warning,
        )

    processed = process_tweets_with_optional_translation(
        relevant_raw,
        sentiment_model=sentiment_model,
        finbert_model_name=finbert_model_name,
        finbert_batch_size=finbert_batch_size,
    )

    if "tweet_id" not in relevant_raw.columns:
        if "id" in relevant_raw.columns:
            relevant_raw["tweet_id"] = relevant_raw["id"].astype(str)
        else:
            relevant_raw = relevant_raw.reset_index(drop=True)
            relevant_raw["tweet_id"] = [f"live_{run_id}_{idx}" for idx in range(len(relevant_raw))]

    if "tweet_id" not in processed.columns:
        if "id" in processed.columns:
            processed["tweet_id"] = processed["id"].astype(str)
        else:
            processed = processed.head(requested_results).reset_index(drop=True)
            relevant_raw = relevant_raw.reset_index(drop=True)
            processed["tweet_id"] = (
                relevant_raw["tweet_id"].astype(str).iloc[: len(processed)].to_list()
            )

    relevance_cols = [
        "tweet_id",
        "is_noise",
        "relevance_score",
        "noise_reason",
        "author_reliability_tier",
        "is_curated_market_author",
    ]
    available_relevance_cols = [col for col in relevance_cols if col in relevant_raw.columns]
    processed = processed.drop(
        columns=[
            col
            for col in available_relevance_cols
            if col in processed.columns and col != "tweet_id"
        ],
        errors="ignore",
    )
    if "tweet_id" in available_relevance_cols:
        processed = processed.merge(
            relevant_raw[available_relevance_cols].drop_duplicates(subset=["tweet_id"]),
            on="tweet_id",
            how="left",
        )
    processed["live_search_query"] = user_query
    processed["x_query"] = combined_query_for_display
    processed["search_mode"] = f"consultas_{search_scope}_preview_then_confirm"
    processed["query_ticker"] = inferred_ticker
    processed["query_name"] = inferred_name
    processed["ingested_at"] = datetime.now(UTC).isoformat()

    summary = summarize_live_tweets(
        processed,
        user_query=user_query,
        use_bedrock=use_bedrock,
        model_id=bedrock_model_id,
        region_name=region_name,
    )

    return LiveSearchPreview(
        rows_requested=safe_max,
        rows_raw=len(labeled),
        rows_relevant=len(processed),
        query=combined_query_for_display,
        run_id=run_id,
        summary=summary,
        bronze_payload=bronze_payload,
        raw_df=labeled,
        relevant_df=processed,
        warning=warning,
    )


def ingest_live_search_preview(
    preview: LiveSearchPreview,
    *,
    bucket: str,
    region_name: str,
) -> DirectLiveSearchResult:
    """Persist a previously previewed live search into medallion S3."""
    bronze_uri = write_twitter_bronze(
        preview.bronze_payload,
        bucket=bucket,
        region_name=region_name,
        run_id=preview.run_id,
    )

    if preview.relevant_df.empty:
        return DirectLiveSearchResult(
            rows_requested=preview.rows_requested,
            rows_raw=preview.rows_raw,
            rows_relevant=0,
            query=preview.query,
            run_id=preview.run_id,
            summary=preview.summary,
            bronze_uri=bronze_uri,
            silver_uri=None,
            gold_uri=None,
            latest_uri=None,
            raw_df=preview.raw_df,
            relevant_df=preview.relevant_df,
        )

    locations = write_medallion_datasets(
        preview.relevant_df,
        bucket=bucket,
        region_name=region_name,
        source="twitter_live",
        run_id=preview.run_id,
        raw_s3_uri=bronze_uri,
    )
    silver = silverize_tweets(
        preview.relevant_df,
        source="twitter_live",
        run_id=preview.run_id,
        raw_s3_uri=bronze_uri,
    )
    latest_uri = update_live_latest(silver, bucket=bucket, region_name=region_name, max_rows=1000)

    logger.info(
        "direct_live_ingest_success run_id=%s rows_raw=%s rows_relevant=%s silver=%s gold=%s latest=%s",
        preview.run_id,
        preview.rows_raw,
        preview.rows_relevant,
        locations.get("silver_uri"),
        locations.get("gold_uri"),
        latest_uri,
    )

    return DirectLiveSearchResult(
        rows_requested=preview.rows_requested,
        rows_raw=preview.rows_raw,
        rows_relevant=preview.rows_relevant,
        query=preview.query,
        run_id=preview.run_id,
        summary=preview.summary,
        bronze_uri=bronze_uri,
        silver_uri=locations.get("silver_uri"),
        gold_uri=locations.get("gold_uri"),
        latest_uri=latest_uri,
        raw_df=preview.raw_df,
        relevant_df=preview.relevant_df,
    )


def run_direct_live_search(
    *,
    user_query: str,
    bearer_token: str,
    bucket: str,
    region_name: str,
    max_results: int,
    sentiment_model: str,
    finbert_model_name: str,
    finbert_batch_size: int,
    use_bedrock: bool,
    bedrock_model_id: str,
    language: str = "auto",
    sort_order: str = "relevancy",
    max_accounts: int = 8,
    search_scope: str = "broad_all_x",
) -> DirectLiveSearchResult:
    """Backward-compatible immediate search+ingest helper."""
    preview = preview_direct_live_search(
        user_query=user_query,
        bearer_token=bearer_token,
        region_name=region_name,
        max_results=max_results,
        sentiment_model=sentiment_model,
        finbert_model_name=finbert_model_name,
        finbert_batch_size=finbert_batch_size,
        use_bedrock=use_bedrock,
        bedrock_model_id=bedrock_model_id,
        language=language,
        sort_order=sort_order,
        max_accounts=max_accounts,
        search_scope=search_scope,
    )
    return ingest_live_search_preview(preview, bucket=bucket, region_name=region_name)
