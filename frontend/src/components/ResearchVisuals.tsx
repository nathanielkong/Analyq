import { useMemo, useState } from 'react'
import { Activity, ChartNoAxesCombined, Newspaper, Scale } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type {
  StockAnalysis,
  StockFundamentals,
  StockHistory,
  StockOutlook,
  StockQuote,
  StockNews,
} from '../types/stocks'

type ResearchVisualsProps = {
  quote: StockQuote
  history: StockHistory | null
  analysis: StockAnalysis | null
  fundamentals: StockFundamentals | null
  outlook: StockOutlook | null
  news?: StockNews | null
  view?: VisualTab
  compact?: boolean
}

export type VisualTab = 'price' | 'fundamentals' | 'news' | 'model'

const tooltipStyle = {
  backgroundColor: '#fffdfa',
  border: '1px solid #d8d0c4',
  borderRadius: '6px',
  color: '#292620',
  boxShadow: '0 10px 24px rgba(83, 70, 53, 0.12)',
}

export function ResearchVisuals({
  quote,
  history,
  analysis,
  fundamentals,
  outlook,
  news,
  view,
  compact = false,
}: ResearchVisualsProps) {
  const [activeTab, setActiveTab] = useState<VisualTab>('price')
  const chartData = useMemo(() => buildPriceChartData(history), [history])
  const availableTabs: Array<{
    id: VisualTab
    label: string
    icon: typeof ChartNoAxesCombined
  }> = []

  if (analysis || chartData.length > 0) {
    availableTabs.push({
      id: 'price',
      label: 'Price & entry',
      icon: ChartNoAxesCombined,
    })
  }

  if (fundamentals) {
    availableTabs.push({
      id: 'fundamentals',
      label: 'Fundamentals',
      icon: Scale,
    })
  }

  if (outlook?.news || news) {
    availableTabs.push({ id: 'news', label: 'News', icon: Newspaper })
  }
  if (outlook) {
    availableTabs.push({ id: 'model', label: 'Model', icon: Activity })
  }

  if (availableTabs.length === 0) {
    return null
  }

  if (view && !availableTabs.some((tab) => tab.id === view)) {
    return null
  }
  const selectedTab =
    view ??
    (availableTabs.some((tab) => tab.id === activeTab)
      ? activeTab
      : availableTabs[0].id)

  return (
    <section className="mt-6 border-t border-neutral-800 pt-5">
      {!view ? (
        <>
          <p className="mb-2 text-xs font-semibold uppercase text-neutral-500">
            Complete research
          </p>
          <div
            aria-label="Research data views"
            className="flex gap-1 overflow-x-auto border-b border-neutral-800"
            role="tablist"
          >
            {availableTabs.map((tab) => {
              const Icon = tab.icon
              const isActive = selectedTab === tab.id

              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-300/40 ${
                    isActive
                      ? 'border-cyan-300 text-cyan-200'
                      : 'border-transparent text-neutral-500 hover:text-neutral-200'
                  }`}
                >
                  <Icon aria-hidden="true" size={16} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </>
      ) : null}

      <div className="pt-5" role={view ? undefined : 'tabpanel'}>
        {selectedTab === 'price' ? (
          <PriceAndEntryView
            quote={quote}
            analysis={analysis}
            chartData={chartData}
            showEntrySummary={!compact}
          />
        ) : null}
        {selectedTab === 'fundamentals' && fundamentals ? (
          <FundamentalsView fundamentals={fundamentals} quote={quote} />
        ) : null}
        {selectedTab === 'news' && (outlook?.news || news) ? (
          <NewsView news={(outlook?.news || news)!} />
        ) : null}
        {selectedTab === 'model' && outlook ? (
          <ModelView outlook={outlook} />
        ) : null}
      </div>
    </section>
  )
}

function PriceAndEntryView({
  quote,
  analysis,
  chartData,
  showEntrySummary,
}: {
  quote: StockQuote
  analysis: StockAnalysis | null
  chartData: PriceChartPoint[]
  showEntrySummary: boolean
}) {
  const entry = analysis?.entry_context
  const entryPlan = entry?.plan

  return (
    <div>
      {entry && showEntrySummary ? (
        <div>
          {entryPlan &&
          entryPlan.preferred_entry_lower !== null &&
          entryPlan.preferred_entry_upper !== null ? (
            <div className="mb-5 border-l-2 border-cyan-300 bg-cyan-300/5 px-4 py-3">
              <p className="text-xs font-semibold uppercase text-cyan-200">
                Technical call: {formatEntrySignal(entryPlan.signal)}
              </p>
              <p className="mt-2 text-base font-semibold text-white">
                Preferred range{' '}
                {formatCurrency(
                  entryPlan.preferred_entry_lower,
                  quote.currency,
                )}{' '}
                -{' '}
                {formatCurrency(
                  entryPlan.preferred_entry_upper,
                  quote.currency,
                )}
              </p>
              <p className="mt-2 text-sm leading-6 text-neutral-400">
                Patient range{' '}
                {formatNullableRange(
                  entryPlan.patient_entry_lower,
                  entryPlan.patient_entry_upper,
                  quote.currency,
                )}
                . The setup weakens below{' '}
                {entryPlan.invalidation_price === null
                  ? '-'
                  : formatCurrency(
                      entryPlan.invalidation_price,
                      quote.currency,
                    )}
                .
              </p>
            </div>
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase text-neutral-500">
                Technical buy-in context
              </p>
              <p className="mt-2 text-sm text-neutral-300">
                Latest price{' '}
                {formatCurrency(entry.reference_price, quote.currency)} is{' '}
                {formatEntryPosition(entry.position)}.
              </p>
            </div>
            <span className="text-xs text-neutral-500">
              Price references, not fair-value estimates
            </span>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {entry.zones.map((zone, index) => (
              <div
                key={zone.label}
                className={`rounded-md border px-4 py-4 ${
                  index === 0
                    ? 'border-cyan-400/35 bg-cyan-400/5'
                    : 'border-amber-400/30 bg-amber-400/5'
                }`}
              >
                <p className="text-xs font-semibold uppercase text-neutral-500">
                  {zone.label}
                </p>
                <p className="mt-2 font-mono text-xl font-semibold text-white">
                  {formatCurrency(zone.lower_price, quote.currency)} -{' '}
                  {formatCurrency(zone.upper_price, quote.currency)}
                </p>
                <p className="mt-2 text-xs leading-5 text-neutral-400">
                  {zone.basis}; central reference{' '}
                  {formatCurrency(zone.reference_price, quote.currency)}.
                </p>
              </div>
            ))}
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-neutral-800 py-4 lg:grid-cols-4">
            <Metric label="RSI 14" value={formatMetric(entry.rsi_14)} />
            <Metric
              label="ATR (typical daily move)"
              value={
                entry.atr_14 === null
                  ? '-'
                  : `${formatCurrency(entry.atr_14, quote.currency)} (${formatPercent(entry.atr_14_pct)})`
              }
            />
            <Metric
              label="20-day range"
              value={formatRange(
                entry.recent_low_20,
                entry.recent_high_20,
                quote.currency,
              )}
            />
            <Metric
              label="Distance from 20-day average"
              value={formatPercent(entry.distance_from_sma_20_pct)}
            />
            <Metric
              label="Upside reference"
              value={
                entryPlan?.upside_reference_price === null ||
                entryPlan?.upside_reference_price === undefined
                  ? '-'
                  : formatCurrency(
                      entryPlan.upside_reference_price,
                      quote.currency,
                    )
              }
            />
            <Metric
              label="Estimated reward / risk"
              value={
                entryPlan?.estimated_reward_risk_ratio === null ||
                entryPlan?.estimated_reward_risk_ratio === undefined
                  ? '-'
                  : `${entryPlan.estimated_reward_risk_ratio.toFixed(2)}x`
              }
            />
          </dl>
          <p className="mt-3 text-xs leading-5 text-neutral-500">
            RSI measures recent momentum: above 70 can mean stretched upward;
            below 30 can mean stretched downward. ATR estimates how much the
            price normally moves in a day.
          </p>
        </div>
      ) : null}

      {chartData.length > 0 ? (
        <div className={entry && showEntrySummary ? 'mt-7' : ''}>
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase text-neutral-500">
                Adjusted price history
              </p>
              <p className="mt-1 text-xs text-neutral-500">
                Close with rolling 20-day and 50-day averages
              </p>
            </div>
            <p className="font-mono text-xs text-neutral-400">
              {chartData[0].date} to {chartData[chartData.length - 1].date}
            </p>
          </div>

          <div className="mt-4 h-72 w-full" aria-label="Historical price chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ left: 0, right: 10 }}>
                <CartesianGrid stroke="#ded6cb" strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  minTickGap={35}
                  stroke="#8f867b"
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  stroke="#8f867b"
                  tick={{ fontSize: 11 }}
                  width={58}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                {entry?.zones.map((zone, index) => (
                  <ReferenceArea
                    key={zone.label}
                    y1={zone.lower_price}
                    y2={zone.upper_price}
                    fill={index === 0 ? '#2f6b55' : '#c68b35'}
                    fillOpacity={0.08}
                    strokeOpacity={0}
                  />
                ))}
                <ReferenceLine
                  y={quote.price}
                  stroke="#292620"
                  strokeDasharray="4 4"
                  label={{
                    value: 'Latest',
                    fill: '#8f867b',
                    fontSize: 11,
                    position: 'insideTopRight',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="close"
                  name="Close"
                  dot={false}
                  stroke="#4f7d69"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="sma20"
                  name="SMA 20"
                  dot={false}
                  connectNulls
                  stroke="#34d399"
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="sma50"
                  name="SMA 50"
                  dot={false}
                  connectNulls
                  stroke="#fbbf24"
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div
            className="mt-5 h-32 w-full"
            aria-label="Historical volume chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ left: 0, right: 10 }}>
                <CartesianGrid stroke="#ded6cb" strokeDasharray="3 3" />
                <XAxis dataKey="date" hide />
                <YAxis
                  stroke="#8f867b"
                  tick={{ fontSize: 10 }}
                  width={58}
                  tickFormatter={(value: number) => compactNumber(value)}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar
                  dataKey="volume"
                  name="Volume"
                  fill="#b8afa4"
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </div>
  )
}

type PercentMetric = {
  name: string
  value: number
}

function FundamentalsView({
  fundamentals,
  quote,
}: {
  fundamentals: StockFundamentals
  quote: StockQuote
}) {
  const valuation = fundamentals.valuation
  const performance = fundamentals.profitability_growth
  const health = fundamentals.financial_health
  const context = fundamentals.market_context
  const currency = fundamentals.company.currency ?? quote.currency
  const scoreRange = Math.max(valuation.metric_count, 1)
  const scorePosition = Math.min(
    100,
    Math.max(0, ((valuation.score + scoreRange) / (scoreRange * 2)) * 100),
  )
  const analystTargetGap =
    valuation.analyst_target_price === null || quote.price === 0
      ? null
      : ((valuation.analyst_target_price - quote.price) / quote.price) * 100
  const performanceData = [
    { name: 'Profit margin', value: performance.profit_margin_pct },
    { name: 'Operating margin', value: performance.operating_margin_pct },
    { name: 'Return on equity', value: performance.return_on_equity_pct },
    {
      name: 'Revenue growth',
      value: performance.quarterly_revenue_growth_yoy_pct,
    },
    {
      name: 'Earnings growth',
      value: performance.quarterly_earnings_growth_yoy_pct,
    },
    { name: 'FCF margin', value: performance.free_cash_flow_margin_pct },
  ].filter((item): item is PercentMetric => item.value !== null)

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-neutral-500">
            Fundamental valuation context
          </p>
          <p className="mt-2 text-lg font-semibold text-white">
            {formatValuationProfile(valuation.profile)}
          </p>
          <p className="mt-1 text-sm leading-6 text-neutral-400">
            Based on {valuation.metric_count} available valuation signals using
            broad absolute thresholds.
          </p>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-neutral-500">
            Valuation multiples compare the share price with earnings, sales, or
            cash flow. Lower is usually cheaper, but fast-growing businesses
            often deserve higher multiples.
          </p>
        </div>
        <div className="text-left sm:text-right">
          <p className="font-mono text-sm text-neutral-200">
            score {valuation.score > 0 ? '+' : ''}
            {valuation.score}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            Financials through{' '}
            {fundamentals.latest_quarter ?? 'latest available period'}
          </p>
        </div>
      </div>

      <div className="mt-5">
        <div className="relative h-3 overflow-hidden rounded-sm bg-neutral-800">
          <div className="absolute inset-y-0 left-0 w-1/3 bg-rose-400/45" />
          <div className="absolute inset-y-0 left-1/3 w-1/3 bg-amber-300/40" />
          <div className="absolute inset-y-0 right-0 w-1/3 bg-emerald-400/45" />
          <span
            aria-label={`Valuation score position ${scorePosition.toFixed(0)} percent`}
            className="absolute top-1/2 h-5 w-1 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-white shadow"
            style={{ left: `${scorePosition}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-[11px] text-neutral-500">
          <span>Premium multiple</span>
          <span>Balanced</span>
          <span>Lower multiple</span>
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-x-5 gap-y-5 border-y border-neutral-800 py-5 lg:grid-cols-4">
        <Metric
          label="Market cap"
          value={formatCompactCurrency(
            valuation.market_capitalization,
            currency,
          )}
        />
        <Metric
          label="Trailing P/E"
          value={formatMultiple(valuation.trailing_pe)}
        />
        <Metric
          label="Forward P/E"
          value={formatMultiple(valuation.forward_pe)}
        />
        <Metric label="PEG ratio" value={formatMetric(valuation.peg_ratio)} />
        <Metric
          label="Price / sales"
          value={formatMultiple(valuation.price_to_sales_ttm)}
        />
        <Metric
          label="Price / book"
          value={formatMultiple(valuation.price_to_book)}
        />
        <Metric
          label="EV / EBITDA"
          value={formatMultiple(valuation.ev_to_ebitda)}
        />
        <Metric
          label="Free-cash-flow yield"
          value={formatPercent(valuation.free_cash_flow_yield_pct)}
        />
      </dl>

      {valuation.analyst_target_price !== null ? (
        <div className="mt-5 flex flex-col gap-2 border-l-2 border-cyan-300 pl-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-neutral-500">
              Analyst target reference
            </p>
            <p className="mt-1 text-sm text-neutral-300">
              Consensus target{' '}
              {formatCurrency(valuation.analyst_target_price, currency)}
            </p>
          </div>
          <span
            className={`font-mono text-sm ${
              (analystTargetGap ?? 0) >= 0
                ? 'text-emerald-300'
                : 'text-rose-300'
            }`}
          >
            {analystTargetGap === null
              ? '-'
              : `${analystTargetGap >= 0 ? '+' : ''}${analystTargetGap.toFixed(1)}% vs latest`}
          </span>
        </div>
      ) : null}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <section>
          <p className="text-xs font-semibold uppercase text-neutral-500">
            Profitability and growth
          </p>
          <p className="mt-2 text-sm text-neutral-400">
            Positive bars indicate positive margins, returns, or year-over-year
            growth.
          </p>

          {performanceData.length > 0 ? (
            <div
              className="mt-4 h-64 w-full"
              aria-label="Profitability and growth chart"
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={performanceData}
                  layout="vertical"
                  margin={{ left: 18, right: 18 }}
                >
                  <CartesianGrid stroke="#ded6cb" strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    stroke="#8f867b"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value: number) => `${value}%`}
                  />
                  <YAxis
                    dataKey="name"
                    type="category"
                    stroke="#8f867b"
                    tick={{ fontSize: 10 }}
                    width={104}
                  />
                  <ReferenceLine x={0} stroke="#8f867b" />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value) => [
                      typeof value === 'number' ? `${value.toFixed(2)}%` : '-',
                      'Value',
                    ]}
                  />
                  <Bar dataKey="value" name="Percent" isAnimationActive={false}>
                    {performanceData.map((item) => (
                      <Cell
                        key={item.name}
                        fill={item.value >= 0 ? '#34d399' : '#fb7185'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-4 text-sm text-neutral-500">
              Profitability and growth metrics are unavailable.
            </p>
          )}
        </section>

        <section>
          <p className="text-xs font-semibold uppercase text-neutral-500">
            Cash flow and financial health
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-5">
            <Metric
              label="Annual free cash flow"
              value={formatCompactCurrency(
                performance.annual_free_cash_flow,
                currency,
              )}
            />
            <Metric
              label="Operating cash flow"
              value={formatCompactCurrency(
                performance.annual_operating_cash_flow,
                currency,
              )}
            />
            <Metric
              label="Cash + investments"
              value={formatCompactCurrency(
                health.cash_and_short_term_investments,
                currency,
              )}
            />
            <Metric
              label="Total debt"
              value={formatCompactCurrency(health.total_debt, currency)}
            />
            <Metric
              label="Net debt"
              value={formatCompactCurrency(health.net_debt, currency)}
            />
            <Metric
              label="Current ratio"
              value={formatMetric(health.current_ratio)}
            />
            <Metric
              label="Debt / equity"
              value={formatMetric(health.debt_to_equity)}
            />
            <Metric label="Beta" value={formatMetric(context.beta)} />
          </dl>

          <div className="mt-5 border-t border-neutral-800 pt-4">
            <p className="text-xs text-neutral-500">52-week trading range</p>
            <p className="mt-1 font-mono text-sm text-neutral-100">
              {formatRange(context.low_52_week, context.high_52_week, currency)}
            </p>
          </div>
        </section>
      </div>

      {valuation.reasons.length > 0 || fundamentals.highlights.length > 0 ? (
        <div className="mt-8 grid gap-6 border-t border-neutral-800 pt-5 lg:grid-cols-2">
          <section>
            <p className="text-xs font-semibold uppercase text-neutral-500">
              Valuation signals
            </p>
            <ul className="mt-3 space-y-2 text-sm leading-6 text-neutral-300">
              {valuation.reasons.map((reason) => (
                <li key={reason} className="border-l border-neutral-700 pl-3">
                  {reason}
                </li>
              ))}
            </ul>
          </section>
          <section>
            <p className="text-xs font-semibold uppercase text-neutral-500">
              Business highlights
            </p>
            <ul className="mt-3 space-y-2 text-sm leading-6 text-neutral-300">
              {fundamentals.highlights.map((highlight) => (
                <li
                  key={highlight}
                  className="border-l border-neutral-700 pl-3"
                >
                  {highlight}
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}

      {fundamentals.warnings.length > 0 ? (
        <details className="mt-6 border-t border-amber-900/60 pt-4 text-sm text-amber-100">
          <summary className="cursor-pointer font-medium">
            Method and data limitations ({fundamentals.warnings.length})
          </summary>
          <ul className="mt-3 space-y-2 text-xs leading-5 text-amber-100/80">
            {fundamentals.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

function NewsView({ news }: { news: StockNews }) {
  const summary = news.summary
  const sentimentData = [
    {
      name: 'Articles',
      positive: summary.positive_count,
      neutral: summary.neutral_count,
      negative: summary.negative_count,
    },
  ]

  return (
    <div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-neutral-500">
            Article sentiment
          </p>
          <p className="mt-2 text-sm text-neutral-300">
            {summary.article_count} relevant articles from{' '}
            {summary.source_count} sources, classified by the backend VADER
            baseline.
          </p>
          <p className="mt-1 text-xs leading-5 text-neutral-500">
            VADER is a simple language model that scores whether headline
            wording sounds positive, neutral, or negative. It measures tone, not
            truth.
          </p>
        </div>
        <span className="font-mono text-sm text-neutral-300">
          weighted score{' '}
          {summary.relevance_weighted_vader_compound?.toFixed(3) ?? '-'}
        </span>
      </div>

      <div className="mt-4 h-28 w-full" aria-label="News sentiment chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sentimentData} layout="vertical">
            <XAxis type="number" hide />
            <YAxis dataKey="name" type="category" hide />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="positive" stackId="sentiment" fill="#34d399" isAnimationActive={false} />
            <Bar dataKey="neutral" stackId="sentiment" fill="#fbbf24" isAnimationActive={false} />
            <Bar dataKey="negative" stackId="sentiment" fill="#fb7185" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-5 divide-y divide-neutral-800 border-y border-neutral-800">
        {news.articles.slice(0, 5).map((article) => (
          <a
            key={`${article.url}-${article.published_at}`}
            href={article.url}
            target="_blank"
            rel="noreferrer"
            className="block py-3 transition hover:bg-neutral-900/60"
          >
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-medium leading-6 text-neutral-200">
                {article.title}
              </p>
              <span
                className={`shrink-0 text-xs font-semibold ${
                  article.vader_label === 'positive'
                    ? 'text-emerald-300'
                    : article.vader_label === 'negative'
                      ? 'text-rose-300'
                      : 'text-amber-200'
                }`}
              >
                {article.vader_label}
              </span>
            </div>
            <p className="mt-1 text-xs text-neutral-500">
              {article.source} · {formatDateTime(article.published_at)}
            </p>
          </a>
        ))}
      </div>
    </div>
  )
}

function ModelView({ outlook }: { outlook: StockOutlook }) {
  const direction = outlook.direction
  const probabilities = [
    {
      name: 'Next close',
      up: direction.up_probability_pct,
      down: direction.down_probability_pct,
    },
  ]
  const accuracy = [
    { name: 'Logistic model', value: direction.validation_accuracy_pct },
    {
      name: 'Strongest baseline',
      value: direction.strongest_baseline_accuracy_pct,
    },
  ]

  return (
    <div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-neutral-500">
            Next-session direction experiment
          </p>
          <p className="mt-2 text-sm text-neutral-300">
            {direction.lean.replaceAll('_', ' ')} with {direction.confidence}{' '}
            confidence; validation status{' '}
            {direction.validation_status.replaceAll('_', ' ')}.
          </p>
          <p className="mt-1 text-xs leading-5 text-neutral-500">
            The model estimates the next closing direction. Validation checks
            how it performed on later data that was not used for training.
          </p>
        </div>
        <span className="font-mono text-sm text-neutral-300">
          edge {formatSignedPercent(direction.accuracy_edge_pct_points)}
        </span>
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div>
          <p className="text-xs font-medium text-neutral-500">
            Estimated direction probability
          </p>
          <div
            className="mt-2 h-32 w-full"
            aria-label="Direction probability chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={probabilities} layout="vertical">
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis dataKey="name" type="category" hide />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="up" stackId="probability" fill="#34d399" isAnimationActive={false} />
                <Bar dataKey="down" stackId="probability" fill="#fb7185" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-neutral-500">
            Walk-forward validation accuracy
          </p>
          <div className="mt-2 h-32 w-full" aria-label="Model validation chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={accuracy}>
                <CartesianGrid stroke="#ded6cb" strokeDasharray="3 3" />
                <XAxis
                  dataKey="name"
                  stroke="#8f867b"
                  tick={{ fontSize: 10 }}
                />
                <YAxis
                  domain={[0, 100]}
                  stroke="#8f867b"
                  tick={{ fontSize: 10 }}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="value" name="Accuracy" isAnimationActive={false}>
                  {accuracy.map((item, index) => (
                    <Cell
                      key={item.name}
                      fill={index === 0 ? '#4f7d69' : '#a69d91'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-neutral-800 py-4 lg:grid-cols-4">
        <Metric
          label="ROC AUC"
          value={formatMetric(direction.validation_roc_auc)}
        />
        <Metric
          label="Brier score"
          value={direction.validation_brier_score.toFixed(3)}
        />
        <Metric
          label="Validation samples"
          value={direction.validation_sample_count.toLocaleString()}
        />
        <Metric
          label="Walk-forward folds"
          value={direction.validation_fold_count.toString()}
        />
      </dl>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-neutral-100">{value}</dd>
    </div>
  )
}

type PriceChartPoint = {
  date: string
  close: number
  sma20: number | null
  sma50: number | null
  volume: number
}

function buildPriceChartData(history: StockHistory | null): PriceChartPoint[] {
  if (!history) {
    return []
  }

  const closes: number[] = []

  return history.bars.map((bar) => {
    closes.push(bar.close)

    return {
      date: bar.timestamp.slice(0, 10),
      close: bar.close,
      sma20: rollingAverage(closes, 20),
      sma50: rollingAverage(closes, 50),
      volume: bar.volume,
    }
  })
}

function rollingAverage(values: number[], window: number): number | null {
  if (values.length < window) {
    return null
  }

  const windowValues = values.slice(-window)
  return windowValues.reduce((total, value) => total + value, 0) / window
}

function formatCurrency(value: number, currency: string) {
  return `${currency} ${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatCompactCurrency(value: number | null, currency: string) {
  if (value === null) {
    return '-'
  }

  return new Intl.NumberFormat('en', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatMultiple(value: number | null) {
  return value === null ? '-' : `${value.toFixed(2)}x`
}

function formatValuationProfile(
  profile: StockFundamentals['valuation']['profile'],
) {
  const labels: Record<typeof profile, string> = {
    lower_multiple: 'Lower-multiple profile',
    balanced: 'Balanced-multiple profile',
    premium_multiple: 'Premium-multiple profile',
    unprofitable: 'Earnings multiples need caution',
    insufficient_data: 'Insufficient valuation data',
  }

  return labels[profile]
}

function formatRange(
  low: number | null,
  high: number | null,
  currency: string,
) {
  if (low === null || high === null) {
    return '-'
  }

  return `${formatCurrency(low, currency)} - ${formatCurrency(high, currency)}`
}

function formatNullableRange(
  low: number | null,
  high: number | null,
  currency: string,
) {
  return low === null || high === null
    ? '-'
    : `${formatCurrency(low, currency)} - ${formatCurrency(high, currency)}`
}

function formatPercent(value: number | null) {
  return value === null ? '-' : `${value.toFixed(2)}%`
}

function formatSignedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)} pp`
}

function formatMetric(value: number | null) {
  return value === null ? '-' : value.toFixed(2)
}

function compactNumber(value: number) {
  return Intl.NumberFormat('en', { notation: 'compact' }).format(value)
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatEntryPosition(
  value: StockAnalysis['entry_context']['position'],
) {
  const labels: Record<typeof value, string> = {
    above_near_term_zone: 'above both calculated pullback zones',
    inside_near_term_zone: 'inside the near-term pullback zone',
    between_reference_zones: 'between the near-term and deeper zones',
    inside_deeper_zone: 'inside the deeper pullback zone',
    below_reference_zones: 'below both calculated pullback zones',
    insufficient_data: 'based on too little history for two complete zones',
  }

  return labels[value]
}

function formatEntrySignal(
  value: StockAnalysis['entry_context']['plan']['signal'],
) {
  const labels: Record<typeof value, string> = {
    wait_for_pullback: 'wait for the preferred range',
    starter_entry: 'starter entry range reached',
    preferred_entry: 'preferred entry range reached',
    avoid_until_stabilizes: 'avoid until price stabilizes',
    insufficient_data: 'not enough data',
  }

  return labels[value]
}
