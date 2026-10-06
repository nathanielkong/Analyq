import { apiGet } from './client'
import type { MarketWatch } from '../types/market'


export function getMarketWatch(limit = 10): Promise<MarketWatch> {
  return apiGet<MarketWatch>(`/market/watch?limit=${limit}`)
}
