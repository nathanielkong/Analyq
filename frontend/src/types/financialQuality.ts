export type CompositeScore = {
  score: number | null
  coverage_pct: number
  validation_status: string
  components: Array<{
    name: string
    score: number | null
    weight: number
    method: string
  }>
}

export type AnnualFinancials = {
  fiscal_date: string
  currency: string | null
  revenue: number | null
  net_income: number | null
  free_cash_flow: number | null
  eps: number | null
  gross_margin_pct: number | null
  operating_margin_pct: number | null
  roe_pct: number | null
}

export type FinancialQuality = {
  years_available: number
  quality: CompositeScore
  growth: CompositeScore
  revenue_cagr_3y_pct: number | null
  revenue_cagr_5y_pct: number | null
  eps_cagr_3y_pct: number | null
  eps_cagr_5y_pct: number | null
  moat_label: string
  moat_evidence: string[]
  warnings: string[]
}

export type PeerComparison = {
  preset: 'value' | 'growth' | 'quality'
  weights: Record<string, number>
  warnings: string[]
  rows: Array<{
    symbol: string
    sector: string | null
    fiscal_date: string | null
    price_sales_ttm: number | null
    price_sales_forward: number | null
    price_fcf_annual: number | null
    ev_ebitda: number | null
    gross_margin_pct: number | null
    quarterly_revenue_growth_yoy_pct: number | null
    sales_growth_multiple: number | null
    quality_score: number | null
    growth_score: number | null
    weighted_score: number | null
    rank: number | null
  }>
}
