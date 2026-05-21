-- Replace the database name if you changed GlueDatabaseName.
USE financial_sentiment_radar;

-- Silver tweet-level live data.
SELECT
  created_at,
  query_ticker,
  primary_ticker,
  author_username,
  sentiment,
  sentiment_model,
  topic,
  text
FROM silver_tweets
WHERE source = 'twitter_live'
  AND ingestion_date >= date_format(current_date - interval '7' day, '%Y-%m-%d')
ORDER BY created_at DESC
LIMIT 100;

-- Gold daily sentiment by ticker.
SELECT
  ticker,
  created_date,
  sum(total) AS total_mentions,
  sum(positive) AS positive_mentions,
  sum(neutral) AS neutral_mentions,
  sum(negative) AS negative_mentions,
  sum(negative) * 1.0 / nullif(sum(total), 0) AS neg_ratio
FROM gold_sentiment_by_ticker_daily
WHERE ingestion_date >= date_format(current_date - interval '30' day, '%Y-%m-%d')
GROUP BY ticker, created_date
ORDER BY created_date DESC, neg_ratio DESC;

-- Manual uploads in silver.
SELECT
  primary_ticker,
  sentiment,
  count(*) AS mentions
FROM silver_tweets
WHERE source = 'manual_upload'
GROUP BY primary_ticker, sentiment
ORDER BY mentions DESC;
