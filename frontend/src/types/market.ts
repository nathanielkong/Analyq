export type MarketWatchSignal =
  | 'news_catalyst'
  | 'session_mover'
  | 'high_activity'
  | 'mixed_attention'

export type MarketSession =
  | 'overnight'
  | 'premarket'
  | 'regular'
  | 'after_hours'
  | 'closed'

export type MarketWatchSentiment =
  | 'bullish'
  | 'mixed'
  | 'bearish'
  | 'unavailable'

export type MarketWatchCandidate = {
  rank: number
  symbol: string
  attention_score: number
  catalyst_score: number
  signal: MarketWatchSignal
  market_session: MarketSession
  price: number | null
  previous_close: number | null
  change_amount: number | null
  change_percent: number | null
  volume: number | null
  snapshot_at: string | null
  news_mentions: number
  average_relevance: number | null
  average_sentiment: number | null
  sentiment: MarketWatchSentiment
  latest_headline: string | null
  latest_source: string | null
  latest_url: string | null
  latest_published_at: string | null
  reasons: string[]
}

export type MarketWatch = {
  generated_at: string
  provider: string
  period_start: string
  period_end: string
  market_snapshot_at: string | null
  market_data_freshness: 'provider_snapshot' | 'combined_snapshot'
  market_session: MarketSession
  snapshot_feed: string | null
  candidates: MarketWatchCandidate[]
  movers: MarketWatchCandidate[]
  news_catalysts: MarketWatchCandidate[]
  warnings: string[]
}
