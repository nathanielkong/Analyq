import type {
  StockAnalysis,
  StockFundamentals,
  StockHistory,
  StockOutlook,
  StockQuote,
  StockNews,
  StockSearchResult,
} from './stocks'

export type AssistantIntent =
  | 'stock_research'
  | 'stock_comparison'
  | 'general_finance'
  | 'unrelated'
  | 'unclear'

export type RequestedStockData =
  | 'quote'
  | 'historical_analysis'
  | 'fundamentals'
  | 'news_sentiment'
  | 'direction_outlook'

export type ResearchTimeHorizon =
  | 'current'
  | 'short_term'
  | 'long_term'
  | 'unspecified'

export type StockPromptInterpretation = {
  intent: AssistantIntent
  stock_queries: string[]
  report_queries?: string[]
  requested_data: RequestedStockData[]
  time_horizon: ResearchTimeHorizon
  keywords: string[]
  requires_clarification: boolean
  clarification_question: string
}

export type AssistantExplanation = {
  visuals?: Array<'price' | 'fundamentals' | 'news' | 'model'>
  title: string
  answer: string
  sections: AssistantAnswerSection[]
}

export type AssistantAnswerSection = {
  label: string
  content: string
}

export type AssistantResearchResponse = {
  instrument?: { kind?: string; note?: string }
  news?: StockNews | null
  horizon_signals?: Array<{
    horizon: string
    signal: string
    method: string
    confidence: string
    evidence: string[]
    invalidation_basis: string
  }>
  interpretation: StockPromptInterpretation
  stock: StockSearchResult
  quote: StockQuote
  history: StockHistory | null
  analysis: StockAnalysis | null
  analysis_error: string | null
  fundamentals: StockFundamentals | null
  fundamentals_error: string | null
  outlook: StockOutlook | null
  outlook_error: string | null
  explanation: AssistantExplanation | null
  explanation_error: string | null
}

export type ResearchReport = {
  id: string
  session_id: string
  symbol: string
  created_at: string
  updated_at: string
  expires_at: string | null
  is_current: boolean
  report_timezone: string
  format_version: number
  research: AssistantResearchResponse
}
