export type PatternName =
  | 'rising_streak_high_rsi'
  | 'falling_streak_low_rsi'
  | 'unusually_large_up_day'
  | 'unusually_large_down_day'

export type PatternHorizon = 1 | 3 | 5

export type ReturnSummary = {
  count: number
  reversals: number
  flat_outcomes: number
  reversal_rate_pct: number | null
  mean_return_pct: number | null
  median_return_pct: number | null
}

export type HorizonBacktest = {
  horizon_bars: PatternHorizon
  status: 'no_observations' | 'small_sample' | 'descriptive_only'
  signal_count: number
  pending_outcomes: number
  overlap_excluded: number
  pattern: ReturnSummary
  baseline: ReturnSummary
  reversal_rate_difference_pp: number | null
  approximate_wilson_95_low_pct: number | null
  approximate_wilson_95_high_pct: number | null
  outcomes: {
    signal_timestamp: string
    outcome_timestamp: string
    forward_return_pct: number
    reversed: boolean
  }[]
}

export type PatternBacktest = {
  symbol: string
  provider: string
  adjusted: boolean
  as_of: string
  start_timestamp: string | null
  data_through: string | null
  completed_bar_count: number
  warnings: string[]
  latest_patterns: {
    status: 'available' | 'insufficient_data' | 'stale' | 'unadjusted'
    signed_close_streak: number | null
    rsi_14: number | null
    daily_return_pct: number | null
    daily_return_zscore: number | null
    checks: { name: PatternName; detected: boolean | null; rule: string }[]
  }
  results: {
    name: PatternName
    rule: string
    reversal_direction: 'up' | 'down'
    initial_active_excluded: number
    horizons: HorizonBacktest[]
  }[]
}
