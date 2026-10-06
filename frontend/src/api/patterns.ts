import { apiGet } from './client'
import type { PatternBacktest } from '../types/patterns'

export function getPatternBacktest(symbol: string, signal?: AbortSignal) {
  return apiGet<PatternBacktest>(
    `/stocks/${encodeURIComponent(symbol)}/patterns/backtest?limit=250`,
    signal,
  )
}
