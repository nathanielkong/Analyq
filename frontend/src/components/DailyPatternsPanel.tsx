import { useEffect, useRef, useState } from 'react'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { getPatternBacktest } from '../api/patterns'
import type {
  PatternBacktest,
  PatternHorizon,
  PatternName,
} from '../types/patterns'

const labels: Record<PatternName, string> = {
  rising_streak_high_rsi: 'Rising streak + high RSI',
  falling_streak_low_rsi: 'Falling streak + low RSI',
  unusually_large_up_day: 'Unusually large up day',
  unusually_large_down_day: 'Unusually large down day',
}
const number = (value: number | null | undefined, unit = '') =>
  value == null || !Number.isFinite(value)
    ? 'Unavailable'
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit}`
const date = (value: string | null) => value?.slice(0, 10) ?? 'Unavailable'

export function DailyPatternsPanel({
  symbol,
  active,
}: {
  symbol: string
  active: boolean
}) {
  const [data, setData] = useState<PatternBacktest | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [horizon, setHorizon] = useState<PatternHorizon>(3)
  const [selected, setSelected] = useState<PatternName>(
    'rising_streak_high_rsi',
  )
  const cached = useRef<{ key: string; data: PatternBacktest } | null>(null)

  useEffect(() => {
    if (!active) return
    const key = `${symbol}:${revision}`
    if (cached.current?.key === key) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setData(null)
    getPatternBacktest(symbol, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return
        cached.current = { key, data: response }
        setData(response)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : 'Pattern data could not be loaded.',
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [active, symbol, revision])

  const result = data?.results.find((item) => item.name === selected)
  const sample = result?.horizons.find((item) => item.horizon_bars === horizon)
  const latest = data?.latest_patterns
  return (
    <section hidden={!active} aria-label={`${symbol} daily patterns`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold">Daily patterns</h3>
          <p className="mt-1 text-sm text-neutral-500">
            Historical study · not a next-day forecast or trading win rate
          </p>
        </div>
        <button
          type="button"
          onClick={() => setRevision((value) => value + 1)}
          disabled={loading}
          aria-label={`Refresh ${symbol} patterns`}
          title="Refresh patterns (market-data quota; provider cache may apply)"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-neutral-800 disabled:opacity-40"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </header>
      {loading ? (
        <p role="status" className="flex items-center gap-2 py-8 text-sm">
          <LoaderCircle size={16} className="animate-spin" />
          Loading pattern history...
        </p>
      ) : null}
      {error ? (
        <div
          role="alert"
          className="my-5 border-l-2 border-rose-700 pl-3 text-sm"
        >
          <p>{error}</p>
          <button
            type="button"
            className="mt-2 underline underline-offset-4"
            onClick={() => setRevision((value) => value + 1)}
          >
            Retry pattern study
          </button>
        </div>
      ) : null}
      {data ? (
        <>
          <p className="mt-4 text-xs leading-5 text-neutral-500">
            {data.completed_bar_count} completed daily bars ·{' '}
            {date(data.start_timestamp)} to {date(data.data_through)} ·{' '}
            {data.provider} · {data.adjusted ? 'Adjusted' : 'Unadjusted'}
            <br />
            Study fetched {new Date(data.as_of).toLocaleString()} · Separate
            from the saved report snapshot
          </p>
          {latest?.status === 'stale' ? (
            <p role="status" className="mt-3 text-sm text-amber-800">
              Stale history: latest detection is withheld. The historical study
              below is not current-market evidence.
            </p>
          ) : null}
          {data.completed_bar_count === 0 ? (
            <p className="py-6 text-sm">
              No completed daily bars are available.
            </p>
          ) : (
            <>
              <dl className="my-5 grid grid-cols-2 gap-4 border-y border-neutral-800 py-4 sm:grid-cols-4">
                {[
                  ['Close streak', number(latest?.signed_close_streak)],
                  ['Last daily return', number(latest?.daily_return_pct, '%')],
                  ['Simple RSI (14)', number(latest?.rsi_14)],
                  ['Move z-score', number(latest?.daily_return_zscore)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-xs text-neutral-500">{label}</dt>
                    <dd className="mt-1 text-sm font-semibold tabular-nums">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
              <fieldset className="mb-4">
                <legend className="mb-2 text-xs text-neutral-500">
                  Outcome horizon (observed daily bars)
                </legend>
                <div className="inline-flex border border-neutral-800">
                  {([1, 3, 5] as const).map((value) => (
                    <label
                      key={value}
                      className={`relative flex h-9 w-20 cursor-pointer items-center justify-center border-r border-neutral-800 text-sm last:border-r-0 ${horizon === value ? 'bg-[#292620] text-[#fffdfa]' : ''}`}
                    >
                      <input
                        type="radio"
                        name={`pattern-horizon-${symbol}`}
                        value={value}
                        checked={horizon === value}
                        onChange={() => setHorizon(value)}
                        className="peer absolute inset-0 h-full w-full cursor-pointer opacity-0"
                      />
                      <span className="pointer-events-none peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-4">
                        {value} {value === 1 ? 'bar' : 'bars'}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div
                className="overflow-x-auto"
                role="region"
                aria-label="Pattern history table"
                tabIndex={0}
              >
                <table className="w-full min-w-[780px] text-left text-xs">
                  <caption className="sr-only">
                    Latest patterns and historical reversal frequencies after{' '}
                    {horizon} daily bars
                  </caption>
                  <thead>
                    <tr>
                      {[
                        'Pattern / reversal',
                        'Latest completed bar',
                        'Historical reversal rate',
                        'Difference',
                        'Mean stock return',
                        'Measured events',
                      ].map((label) => (
                        <th
                          key={label}
                          scope="col"
                          className="px-2 py-3 font-medium"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((item) => {
                      const stats = item.horizons.find(
                        (entry) => entry.horizon_bars === horizon,
                      )
                      const detected = latest?.checks.find(
                        (entry) => entry.name === item.name,
                      )?.detected
                      return (
                        <tr
                          key={item.name}
                          className="border-t border-neutral-800 align-top"
                        >
                          <th
                            scope="row"
                            className="max-w-48 px-2 py-4 font-medium"
                          >
                            {labels[item.name]}
                            <span className="mt-1 block font-normal text-neutral-500">
                              {item.reversal_direction === 'down'
                                ? 'Lower'
                                : 'Higher'}{' '}
                              final close
                            </span>
                          </th>
                          <td className="px-2 py-4">
                            {detected == null
                              ? 'Unavailable'
                              : detected
                                ? 'Detected'
                                : 'Not detected'}
                          </td>
                          <td className="min-w-48 px-2 py-4">
                            <RateBar
                              label="Pattern"
                              value={stats?.pattern.reversal_rate_pct ?? null}
                              color="#3e786b"
                            />
                            <RateBar
                              label="Baseline"
                              value={stats?.baseline.reversal_rate_pct ?? null}
                              color="#8b8792"
                            />
                          </td>
                          <td className="px-2 py-4 tabular-nums">
                            {number(stats?.reversal_rate_difference_pp, ' pp')}
                          </td>
                          <td className="px-2 py-4 tabular-nums">
                            {number(stats?.pattern.mean_return_pct, '%')}
                          </td>
                          <td className="px-2 py-4 tabular-nums">
                            {stats?.pattern.count ?? 0}
                            <span className="mt-1 block text-neutral-500">
                              {stats?.status === 'no_observations'
                                ? 'No observations'
                                : stats?.status === 'small_sample'
                                  ? 'Small sample'
                                  : 'Descriptive only'}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-5 text-neutral-500">
                A reversal is an opposite final close, not any temporary dip or
                rebound. Baseline includes all evaluable dates. Mean return is
                the stock’s return, not trade profit. Fewer than 30 events is a
                small sample; larger samples still do not prove an edge.
              </p>
              <section
                className="mt-6 border-t border-neutral-800 pt-4"
                aria-label="Pattern evidence"
              >
                <label
                  className="block text-sm font-semibold"
                  htmlFor={`pattern-evidence-${symbol}`}
                >
                  Evidence and uncertainty
                </label>
                <select
                  id={`pattern-evidence-${symbol}`}
                  value={selected}
                  onChange={(event) =>
                    setSelected(event.target.value as PatternName)
                  }
                  className="mt-3 min-h-10 w-full min-w-0 rounded-md border border-neutral-800 bg-transparent px-2 text-sm sm:max-w-sm"
                >
                  {data.results.map((item) => (
                    <option key={item.name} value={item.name}>
                      {labels[item.name]}
                    </option>
                  ))}
                </select>
                <p className="mt-3 text-xs leading-5 text-neutral-500">
                  {result?.rule}
                </p>
                {sample ? (
                  <>
                    <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
                      {[
                        [
                          'Reversals / measured',
                          `${sample.pattern.reversals} / ${sample.pattern.count}`,
                        ],
                        [
                          'Approx. 95% interval',
                          sample.approximate_wilson_95_low_pct == null ||
                          sample.approximate_wilson_95_high_pct == null
                            ? 'Unavailable'
                            : `${number(sample.approximate_wilson_95_low_pct, '%')} to ${number(sample.approximate_wilson_95_high_pct, '%')}`,
                        ],
                        [
                          'Median stock return',
                          number(sample.pattern.median_return_pct, '%'),
                        ],
                        ['Pending outcomes', String(sample.pending_outcomes)],
                        ['Overlaps excluded', String(sample.overlap_excluded)],
                        [
                          'Initially active excluded',
                          String(result?.initial_active_excluded ?? 0),
                        ],
                        ['Baseline dates', String(sample.baseline.count)],
                        ['Signal starts', String(sample.signal_count)],
                      ].map(([label, value]) => (
                        <div key={label}>
                          <dt className="text-xs text-neutral-500">{label}</dt>
                          <dd className="mt-1 tabular-nums">{value}</dd>
                        </div>
                      ))}
                    </dl>
                    <p className="mt-3 text-xs leading-5 text-neutral-500">
                      The interval describes sampling uncertainty, not the
                      probability of your next trade. Serial dependence can make
                      it too narrow.
                    </p>
                    <details className="mt-4 text-xs">
                      <summary className="cursor-pointer">
                        Dated outcomes ({sample.outcomes.length})
                      </summary>
                      {sample.outcomes.length ? (
                        <div
                          className="mt-2 max-h-72 overflow-auto"
                          role="region"
                          aria-label="Dated pattern outcomes"
                          tabIndex={0}
                        >
                          <table className="w-full min-w-[440px] text-left">
                            <thead>
                              <tr>
                                {[
                                  'Signal date',
                                  'Outcome date',
                                  'Stock return',
                                  'Reversal',
                                ].map((label) => (
                                  <th
                                    key={label}
                                    scope="col"
                                    className="p-2 font-medium"
                                  >
                                    {label}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {sample.outcomes.map((outcome) => (
                                <tr
                                  key={outcome.signal_timestamp}
                                  className="border-t border-neutral-800"
                                >
                                  <td className="p-2">
                                    {date(outcome.signal_timestamp)}
                                  </td>
                                  <td className="p-2">
                                    {date(outcome.outcome_timestamp)}
                                  </td>
                                  <td className="p-2">
                                    {number(outcome.forward_return_pct, '%')}
                                  </td>
                                  <td className="p-2">
                                    {outcome.reversed ? 'Yes' : 'No'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="py-3">
                          No completed, non-overlapping events for this horizon.
                        </p>
                      )}
                    </details>
                  </>
                ) : (
                  <p className="mt-3 text-sm">This horizon is unavailable.</p>
                )}
              </section>
            </>
          )}
          <details className="mt-5 text-xs text-neutral-500">
            <summary className="cursor-pointer">
              Methods and data limitations
            </summary>
            <ul className="mt-3 list-disc space-y-2 pl-4">
              {data.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </details>
        </>
      ) : null}
    </section>
  )
}

function RateBar({
  label,
  value,
  color,
}: {
  label: string
  value: number | null
  color: string
}) {
  return (
    <div className="mb-2 last:mb-0">
      <div className="mb-1 flex justify-between gap-3">
        <span>{label}</span>
        <span className="tabular-nums">{number(value, '%')}</span>
      </div>
      {value != null && Number.isFinite(value) ? (
        <div aria-hidden="true" className="h-1.5 w-full bg-neutral-200">
          <div
            className="h-full"
            style={{
              width: `${Math.min(100, Math.max(0, value))}%`,
              backgroundColor: color,
            }}
          />
        </div>
      ) : null}
    </div>
  )
}
