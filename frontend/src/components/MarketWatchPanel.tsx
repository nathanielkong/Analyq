import { useCallback, useEffect, useState } from 'react'
import {
  ExternalLink,
  Newspaper,
  RefreshCw,
  Search,
  TrendingUp,
  X,
} from 'lucide-react'

import { getMarketWatch } from '../api/market'
import type { MarketWatch } from '../types/market'

type RequestState = 'loading' | 'success' | 'error'
type MarketWatchView = 'movers' | 'news'

export function MarketWatchPanel({
  onClose,
  onResearch,
}: {
  onClose?: () => void
  onResearch: (symbol: string) => void
}) {
  const [requestState, setRequestState] = useState<RequestState>('loading')
  const [marketWatch, setMarketWatch] = useState<MarketWatch | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<MarketWatchView>('movers')

  const loadMarketWatch = useCallback(async () => {
    setRequestState('loading')
    setErrorMessage(null)

    try {
      const result = await getMarketWatch()
      setMarketWatch(result)
      setRequestState('success')
    } catch (error) {
      setRequestState('error')
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load stocks drawing market attention.',
      )
    }
  }, [])

  const visibleCandidates = marketWatch
    ? activeView === 'movers'
      ? marketWatch.movers
      : marketWatch.news_catalysts
    : []

  useEffect(() => {
    let ignoreResponse = false

    getMarketWatch()
      .then((result) => {
        if (ignoreResponse) {
          return
        }

        setMarketWatch(result)
        setRequestState('success')
      })
      .catch((error: unknown) => {
        if (ignoreResponse) {
          return
        }

        setRequestState('error')
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to load stocks drawing market attention.',
        )
      })

    return () => {
      ignoreResponse = true
    }
  }, [])

  return (
    <section className="pb-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-neutral-500">Market watch</p>
          <h3 className="mt-2 font-serif text-3xl font-semibold text-white">
            Movers and news catalysts
          </h3>
          <p className="mt-1 text-sm text-neutral-500">
            See the largest moves from the previous close or names hit by
            important news.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            aria-label="Refresh market watch"
            title="Refresh market watch"
            onClick={() => void loadMarketWatch()}
            disabled={requestState === 'loading'}
            className="flex h-9 w-9 items-center justify-center rounded-md border border-neutral-800 text-neutral-400 transition hover:border-cyan-400/50 hover:text-cyan-200 focus:outline-none focus:ring-2 focus:ring-cyan-300/40 disabled:opacity-50"
          >
            <RefreshCw
              aria-hidden="true"
              size={16}
              className={requestState === 'loading' ? 'animate-spin' : ''}
            />
          </button>
          {onClose ? (
            <button
              type="button"
              aria-label="Close market watch"
              title="Close market watch"
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-md border border-neutral-800 text-neutral-400 transition hover:border-neutral-600 hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
            >
              <X aria-hidden="true" size={17} />
            </button>
          ) : null}
        </div>
      </div>

      {requestState === 'loading' && !marketWatch ? (
        <div className="mt-5 space-y-2" aria-live="polite">
          {[0, 1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-20 animate-pulse rounded-md border border-neutral-800 bg-neutral-900"
            />
          ))}
        </div>
      ) : null}

      {requestState === 'error' ? (
        <div className="mt-5 rounded-md border border-rose-900 bg-rose-950 px-4 py-3 text-sm text-rose-100">
          {errorMessage}
        </div>
      ) : null}

      {marketWatch ? (
        <div className="mt-5">
          <div className="flex flex-col gap-1 border-y border-neutral-800 py-3 text-xs text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Updated {formatDateTime(marketWatch.generated_at)} ·{' '}
              {formatSession(marketWatch.market_session)}
            </span>
            <span>
              {marketWatch.snapshot_feed
                ? `Alpaca ${marketWatch.snapshot_feed} snapshot`
                : 'Provider snapshot'}
            </span>
          </div>

          <div
            aria-label="Market watch views"
            className="mt-4 inline-flex border border-neutral-800 bg-neutral-900"
            role="tablist"
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeView === 'movers'}
              onClick={() => setActiveView('movers')}
              className={`flex h-9 items-center gap-2 px-3 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-300/40 ${
                activeView === 'movers'
                  ? 'bg-cyan-300 text-neutral-950'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <TrendingUp aria-hidden="true" size={15} />
              Biggest movers
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeView === 'news'}
              onClick={() => setActiveView('news')}
              className={`flex h-9 items-center gap-2 border-l border-neutral-800 px-3 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-300/40 ${
                activeView === 'news'
                  ? 'bg-cyan-300 text-neutral-950'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Newspaper aria-hidden="true" size={15} />
              News catalysts
            </button>
          </div>

          <div className="mt-3 divide-y divide-neutral-800 border-b border-neutral-800">
            {visibleCandidates.map((candidate) => (
              <article
                key={candidate.symbol}
                data-symbol={candidate.symbol}
                className="grid gap-3 py-4 md:grid-cols-[48px_100px_minmax(0,1fr)_120px] md:items-center"
              >
                <span className="font-mono text-sm text-neutral-600">
                  {candidate.rank.toString().padStart(2, '0')}
                </span>

                <div>
                  <p className="font-mono text-base font-semibold text-white">
                    {candidate.symbol}
                  </p>
                  <p className="mt-1 font-mono text-xs text-neutral-400">
                    {candidate.price === null
                      ? 'price unavailable'
                      : formatPrice(candidate.price)}
                  </p>
                  <p
                    className={`mt-1 font-mono text-xs ${
                      (candidate.change_percent ?? 0) > 0
                        ? 'text-emerald-300'
                        : (candidate.change_percent ?? 0) < 0
                          ? 'text-rose-300'
                          : 'text-neutral-500'
                    }`}
                  >
                    {candidate.change_percent === null
                      ? 'news signal'
                      : formatSignedPercent(candidate.change_percent)}
                  </p>
                  <p className="mt-1 text-[11px] text-neutral-600">
                    vs previous close
                  </p>
                </div>

                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300">
                      {formatSignal(candidate.signal)}
                    </span>
                    <span
                      className={`text-xs font-semibold ${
                        candidate.sentiment === 'bullish'
                          ? 'text-emerald-300'
                          : candidate.sentiment === 'bearish'
                            ? 'text-rose-300'
                            : 'text-amber-200'
                      }`}
                    >
                      {candidate.sentiment}
                    </span>
                    <span className="text-xs text-neutral-500">
                      {candidate.news_mentions} news mentions
                    </span>
                  </div>

                  {candidate.latest_headline ? (
                    candidate.latest_url ? (
                      <a
                        href={candidate.latest_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 flex min-w-0 items-start gap-1.5 text-sm leading-5 text-neutral-300 hover:text-cyan-200"
                      >
                        <span className="line-clamp-2">
                          {candidate.latest_headline}
                        </span>
                        <ExternalLink
                          aria-hidden="true"
                          size={13}
                          className="mt-1 shrink-0"
                        />
                      </a>
                    ) : (
                      <p className="mt-2 line-clamp-2 text-sm leading-5 text-neutral-300">
                        {candidate.latest_headline}
                      </p>
                    )
                  ) : (
                    <p className="mt-2 text-sm text-neutral-500">
                      Market activity signal without a matching broad-news
                      headline.
                    </p>
                  )}

                  {candidate.reasons.length > 0 ? (
                    <ul className="mt-2 space-y-1 text-xs leading-5 text-neutral-500">
                      {candidate.reasons.slice(0, 2).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}

                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-neutral-800">
                    <div
                      className="h-full rounded-full bg-cyan-300"
                      style={{
                        width: `${Math.max(
                          3,
                          Math.min(
                            100,
                            activeView === 'news'
                              ? candidate.catalyst_score
                              : candidate.attention_score,
                          ),
                        )}%`,
                      }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-neutral-600">
                    {activeView === 'news' ? 'catalyst' : 'attention'} score{' '}
                    {(activeView === 'news'
                      ? candidate.catalyst_score
                      : candidate.attention_score
                    ).toFixed(1)}
                  </p>
                </div>

                <button
                  type="button"
                  aria-label={`Research ${candidate.symbol}`}
                  onClick={() => onResearch(candidate.symbol)}
                  className="flex h-9 items-center justify-center gap-2 rounded-md border border-neutral-700 px-3 text-sm font-medium text-neutral-200 transition hover:border-cyan-400/50 hover:text-cyan-200 focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
                >
                  <Search aria-hidden="true" size={15} />
                  Research
                </button>
              </article>
            ))}

            {visibleCandidates.length === 0 ? (
              <p className="py-6 text-sm text-neutral-500">
                No candidates are available for this view right now.
              </p>
            ) : null}
          </div>

          {marketWatch.warnings.length > 0 ? (
            <p className="mt-3 text-xs leading-5 text-neutral-600">
              {marketWatch.warnings.join(' ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatSignedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatSignal(value: string) {
  return value.replaceAll('_', ' ')
}

function formatSession(value: MarketWatch['market_session']) {
  const labels: Record<typeof value, string> = {
    overnight: 'Overnight session',
    premarket: 'Premarket session',
    regular: 'Regular session',
    after_hours: 'After-hours session',
    closed: 'Market closed',
  }

  return labels[value]
}

function formatPrice(value: number) {
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}
