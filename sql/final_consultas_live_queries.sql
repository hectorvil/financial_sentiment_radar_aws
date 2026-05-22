-- Tweets live no-ruido en Silver
SELECT
  created_at,
  author_username,
  primary_ticker,
  query_ticker,
  sentiment,
  sentiment_confidence,
  topic,
  relevance_score,
  text
FROM financial_sentiment_radar.silver_tweets
WHERE source = 'twitter_live'
  AND coalesce(is_noise, false) = false
ORDER BY created_at DESC
LIMIT 100;

-- Agregados Gold por ticker/fuente/fecha
SELECT
  source,
  ticker,
  created_date,
  total,
  positive,
  neutral,
  negative,
  pos_ratio,
  neu_ratio,
  neg_ratio
FROM financial_sentiment_radar.gold_sentiment_by_ticker_daily
WHERE source IN ('twitter_live', 'manual_upload')
ORDER BY created_date DESC, source, ticker;

-- Comparación live vs batch
SELECT
  source,
  ticker,
  sum(total) AS total_mentions,
  sum(positive) AS positive_mentions,
  sum(neutral) AS neutral_mentions,
  sum(negative) AS negative_mentions,
  sum(negative) * 1.0 / nullif(sum(total), 0) AS neg_ratio
FROM financial_sentiment_radar.gold_sentiment_by_ticker_daily
GROUP BY source, ticker
ORDER BY neg_ratio DESC, total_mentions DESC;
