import type { AnnualFinancials, FinancialQuality } from './financialQuality'

export type StockQuote = {
  symbol: string
  company_name: string | null
  price: number
  currency: string
  change: number | null
  change_percent: number | null
  volume: number | null
  latest_trading_day: string | null
  previous_close: number | null
  open: number | null
  high: number | null
  low: number | null
  source: string
}

export type StockSearchResult = {
  symbol: string
  name: string
  type: string
  region: string
  currency: string
  match_score: number | null
}

export type StockHistoryBar = {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  source: string
}

export type StockHistory = {
  symbol: string
  provider: string
  timeframe: string
  adjusted: boolean
  requested_bar_count: number
  warnings: string[]
  bars: StockHistoryBar[]
}

export type StockAnalysisTrend =
  | 'uptrend'
  | 'downtrend'
  | 'sideways'
  | 'insufficient_data'

export type StockAnalysisRiskLevel =
  | 'low'
  | 'medium'
  | 'high'
  | 'insufficient_data'

export type StockEntryPosition =
  | 'above_near_term_zone'
  | 'inside_near_term_zone'
  | 'between_reference_zones'
  | 'inside_deeper_zone'
  | 'below_reference_zones'
  | 'insufficient_data'

export type TechnicalEntryZone = {
  label: string
  lower_price: number
  upper_price: number
  reference_price: number
  basis: string
}

export type TechnicalEntryPlan = {
  signal:
    | 'wait_for_pullback'
    | 'starter_entry'
    | 'preferred_entry'
    | 'avoid_until_stabilizes'
    | 'insufficient_data'
  preferred_entry_lower: number | null
  preferred_entry_upper: number | null
  patient_entry_lower: number | null
  patient_entry_upper: number | null
  upside_reference_price: number | null
  invalidation_price: number | null
  estimated_reward_risk_ratio: number | null
  method: string
}

export type StockEntryContext = {
  reference_price: number
  position: StockEntryPosition
  atr_14: number | null
  atr_14_pct: number | null
  rsi_14: number | null
  distance_from_sma_20_pct: number | null
  distance_from_sma_50_pct: number | null
  recent_low_20: number | null
  recent_high_20: number | null
  recent_low_50: number | null
  recent_high_50: number | null
  zones: TechnicalEntryZone[]
  plan: TechnicalEntryPlan
  notes: string[]
}

export type StockAnalysis = {
  analysis_version: string
  symbol: string
  provider: string
  timeframe: string
  mode: 'historical'
  as_of: string
  data_through: string
  adjusted: boolean
  bar_count: number
  sample_sufficient: boolean
  trend_sample_sufficient: boolean
  start_timestamp: string
  end_timestamp: string
  first_close: number
  latest_close: number
  period_return_pct: number
  compound_average_daily_return_pct: number
  annualized_volatility_pct: number | null
  moving_average_20: number | null
  moving_average_50: number | null
  max_drawdown_pct: number
  trend: StockAnalysisTrend
  risk_level: StockAnalysisRiskLevel
  entry_context: StockEntryContext
  reasons: string[]
  warnings: string[]
}

export type StockSentimentLabel =
  | 'positive'
  | 'neutral'
  | 'negative'
  | 'insufficient_data'

export type StockNewsArticle = {
  title: string
  summary: string
  url: string
  source: string
  source_domain: string | null
  published_at: string
  authors: string[]
  topics: Array<{
    name: string
    relevance_score: number | null
  }>
  relevance_score: number | null
  provider_sentiment_score: number | null
  provider_sentiment_label: string | null
  vader_positive: number
  vader_neutral: number
  vader_negative: number
  vader_compound: number
  vader_label: StockSentimentLabel
}

export type StockNews = {
  sentiment_version: string
  symbol: string
  provider: string
  model: string
  fetched_at: string
  period_start: string
  period_end: string
  article_coverage_start: string | null
  article_coverage_end: string | null
  requested_limit: number
  result_limit_reached: boolean
  summary: {
    article_count: number
    positive_count: number
    neutral_count: number
    negative_count: number
    source_count: number
    average_vader_compound: number | null
    relevance_weighted_vader_compound: number | null
    average_provider_sentiment: number | null
    label: StockSentimentLabel
  }
  articles: StockNewsArticle[]
  warnings: string[]
}

export type StockDirection = {
  model_version: string
  model_type: 'logistic_regression'
  symbol: string
  benchmark_symbol: string
  target: string
  horizon: string
  generated_at: string
  data_through: string
  lean: 'leaning_up' | 'leaning_down' | 'mixed'
  confidence: 'low' | 'moderate'
  up_probability_pct: number
  down_probability_pct: number
  training_start: string
  training_end: string
  training_sample_count: number
  validation_sample_count: number
  validation_fold_count: number
  validation_status: 'validated_edge' | 'inconclusive' | 'no_edge'
  validation_accuracy_pct: number
  validation_balanced_accuracy_pct: number
  validation_precision_pct: number
  validation_recall_pct: number
  validation_f1_pct: number
  validation_roc_auc: number | null
  baseline_accuracy_pct: number
  momentum_baseline_accuracy_pct: number
  benchmark_baseline_accuracy_pct: number
  strongest_baseline_accuracy_pct: number
  accuracy_edge_pct_points: number
  validation_brier_score: number
  baseline_brier_score: number
  validation_log_loss: number
  observed_up_rate_pct: number
  decisive_prediction_count: number
  decisive_coverage_pct: number
  decisive_accuracy_pct: number | null
  confusion_matrix: {
    true_down_predicted_down: number
    true_down_predicted_up: number
    true_up_predicted_down: number
    true_up_predicted_up: number
  }
  folds: Array<{
    fold: number
    training_sample_count: number
    validation_sample_count: number
    validation_start: string
    validation_end: string
    accuracy_pct: number
    balanced_accuracy_pct: number
    brier_score: number
    roc_auc: number | null
    majority_baseline_accuracy_pct: number
    momentum_baseline_accuracy_pct: number
    benchmark_baseline_accuracy_pct: number
  }>
  calibration: Array<{
    lower_probability_pct: number
    upper_probability_pct: number
    sample_count: number
    average_predicted_up_pct: number
    observed_up_pct: number
  }>
  feature_stability: Array<{
    feature_name: string
    mean_standardized_coefficient: number
    coefficient_std_dev: number
    sign_consistency_pct: number
  }>
  news_features_used: boolean
  feature_names: string[]
  latest_feature_values: Record<string, number>
  warnings: string[]
}

export type StockOutlook = {
  symbol: string
  benchmark_symbol: string
  news: StockNews
  direction: StockDirection
}

export type ValuationProfile =
  | 'lower_multiple'
  | 'balanced'
  | 'premium_multiple'
  | 'unprofitable'
  | 'insufficient_data'

export type StockFundamentals = {
  annual_financials?: AnnualFinancials[]
  financial_quality?: FinancialQuality | null
  fundamentals_version: string
  symbol: string
  provider: string
  fetched_at: string
  latest_quarter: string | null
  company: {
    name: string | null
    asset_type: string | null
    exchange: string | null
    currency: string | null
    country: string | null
    sector: string | null
    industry: string | null
    fiscal_year_end: string | null
    description: string | null
  }
  valuation: {
    profile: ValuationProfile
    score: number
    metric_count: number
    market_capitalization: number | null
    trailing_pe: number | null
    forward_pe: number | null
    peg_ratio: number | null
    price_to_sales_ttm: number | null
    price_to_book: number | null
    ev_to_revenue: number | null
    ev_to_ebitda: number | null
    free_cash_flow_yield_pct: number | null
    dividend_yield_pct: number | null
    analyst_target_price: number | null
    reasons: string[]
  }
  profitability_growth: {
    revenue_ttm: number | null
    gross_profit_ttm: number | null
    ebitda: number | null
    eps: number | null
    diluted_eps_ttm: number | null
    profit_margin_pct: number | null
    operating_margin_pct: number | null
    return_on_assets_pct: number | null
    return_on_equity_pct: number | null
    quarterly_revenue_growth_yoy_pct: number | null
    quarterly_earnings_growth_yoy_pct: number | null
    annual_operating_cash_flow: number | null
    annual_capital_expenditures: number | null
    annual_free_cash_flow: number | null
    free_cash_flow_margin_pct: number | null
    cash_flow_period_end: string | null
  }
  financial_health: {
    balance_sheet_period_end: string | null
    total_assets: number | null
    total_current_assets: number | null
    total_current_liabilities: number | null
    total_liabilities: number | null
    cash_and_short_term_investments: number | null
    total_debt: number | null
    net_debt: number | null
    total_shareholder_equity: number | null
    current_ratio: number | null
    debt_to_equity: number | null
  }
  market_context: {
    beta: number | null
    high_52_week: number | null
    low_52_week: number | null
  }
  highlights: string[]
  warnings: string[]
}
