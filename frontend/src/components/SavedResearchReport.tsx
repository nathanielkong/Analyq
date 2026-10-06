import { lazy, Suspense, useEffect, useId, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { RefreshCw } from 'lucide-react'
import type { ResearchReport } from '../types/assistant'
import type { VisualTab } from './ResearchVisuals'
import { DailyPatternsPanel } from './DailyPatternsPanel'

const reportSections = [
  'Market report',
  'Market outlook',
  'Fundamentals',
  'Sentiment report',
  'News report',
  'Bull and bear case',
  'Investment plan',
  'Risk management',
]
const sectionCharts: Record<string, VisualTab> = {
  overview: 'price',
  'Market report': 'price',
  'Market outlook': 'model',
  Fundamentals: 'fundamentals',
  'Sentiment report': 'news',
  'Investment plan': 'price',
  'Risk management': 'model',
}

const ResearchVisuals = lazy(() =>
  import('./ResearchVisuals').then((module) => ({
    default: module.ResearchVisuals,
  })),
)
const num = (value: number | null | undefined) =>
  value == null
    ? '-'
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 })

export function SavedResearchReport({
  report,
  busy,
  onRefresh,
}: {
  report: ResearchReport
  busy: boolean
  onRefresh: (report: ResearchReport) => void
}) {
  const [section, setSection] = useState('overview')
  const [checkedAt, setCheckedAt] = useState(() => Date.now())
  useEffect(() => {
    if (!report.expires_at) return
    const delay = Math.max(
      0,
      new Date(report.expires_at).getTime() - Date.now() + 1,
    )
    const timer = window.setTimeout(() => setCheckedAt(Date.now()), delay)
    return () => window.clearTimeout(timer)
  }, [report.expires_at])
  const tabId = useId()
  const data = report.research
  const financials = data.fundamentals
  const quality = financials?.financial_quality
  const sections = data.explanation?.sections ?? []
  const activeNarrative = sections.find((item) => item.label === section)
  const tabs = [
    ...new Set([
      'overview',
      'Daily patterns',
      ...reportSections,
      ...sections.map((item) => item.label),
      'financial scores',
    ]),
  ]
  const expired =
    !report.is_current ||
    !report.expires_at ||
    new Date(report.expires_at).getTime() <= checkedAt
  return (
    <article className="mx-auto w-full max-w-4xl py-5">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-neutral-800 pb-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-neutral-500">
            {report.symbol} · Market analysis
          </p>
          <h2 className="mt-2 break-words font-serif text-2xl">
            {data.stock.name}
          </h2>
          <p className="mt-2 text-xs text-neutral-500">
            Report generated {new Date(report.updated_at).toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            {expired
              ? 'Archived snapshot · refresh needed for current research'
              : `Daily snapshot · reusable until ${new Date(report.expires_at!).toLocaleString('en-AU', { timeZone: report.report_timezone })} (${report.report_timezone})`}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            Price as of{' '}
            {data.quote.latest_trading_day
              ? new Date(data.quote.latest_trading_day).toLocaleString()
              : 'unavailable'}{' '}
            · {data.quote.source}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <strong className="text-xl tabular-nums">
            {data.quote.currency} {num(data.quote.price)}
          </strong>
          <button
            type="button"
            disabled={busy}
            onClick={() => onRefresh(report)}
            aria-label={`Refresh ${report.symbol} report`}
            title="Refresh report (uses API credits; provider caches may apply)"
            className="flex h-9 w-9 items-center justify-center rounded-md border border-neutral-800 disabled:opacity-40"
          >
            <RefreshCw size={16} className={busy ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>
      {data.instrument?.kind === 'fund' ? (
        <p className="mt-4 text-sm text-neutral-500">{data.instrument.note}</p>
      ) : null}
      <div
        role="tablist"
        aria-label="Report sections"
        className="mt-4 flex overflow-x-auto border-b border-neutral-800"
      >
        {tabs.map((label, index) => (
          <button
            key={label}
            role="tab"
            aria-selected={section === label}
            aria-controls={`${tabId}-panel`}
            id={`${tabId}-tab-${index}`}
            tabIndex={section === label ? 0 : -1}
            type="button"
            onClick={() => setSection(label)}
            onKeyDown={(event) => {
              const next =
                event.key === 'ArrowRight'
                  ? (index + 1) % tabs.length
                  : event.key === 'ArrowLeft'
                    ? (index + tabs.length - 1) % tabs.length
                    : event.key === 'Home'
                      ? 0
                      : event.key === 'End'
                        ? tabs.length - 1
                        : null
              if (next === null) return
              event.preventDefault()
              setSection(tabs[next])
              document.getElementById(`${tabId}-tab-${next}`)?.focus()
            }}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm ${section === label ? 'border-[#292620] font-semibold' : 'border-transparent text-neutral-500'}`}
          >
            {label === 'overview'
              ? 'Overview'
              : label === 'financial scores'
                ? 'Financial scores'
                : label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${tabId}-panel`}
        aria-labelledby={`${tabId}-tab-${tabs.indexOf(section)}`}
        className="min-w-0 pt-5"
      >
        {section === 'overview' ? (
          <>
            {data.explanation ? (
              <div className="assistant-answer">
                <ReactMarkdown>{data.explanation.answer}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-neutral-500">
                {data.explanation_error ??
                  'Narrative unavailable. Collected data is shown below.'}
              </p>
            )}
          </>
        ) : section === 'Daily patterns' ? null : section ===
          'Market outlook' ? (
          <>
            <ReportNarrative content={activeNarrative?.content} />
            <div className="mt-6 grid gap-5 border-y border-neutral-800 py-4 sm:grid-cols-3">
              {data.horizon_signals?.map((signal) => (
                <section key={signal.horizon} className="min-w-0">
                  <h3 className="text-xs font-semibold uppercase text-neutral-500">
                    {signal.horizon.replaceAll('_', ' ')}
                  </h3>
                  <p className="mt-2 break-words text-sm font-semibold">
                    {signal.signal.replaceAll('_', ' ')}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500">
                    {signal.confidence.replaceAll('_', ' ')}
                  </p>
                  <details className="mt-2 text-xs leading-5">
                    <summary className="cursor-pointer">Evidence</summary>
                    <p>{signal.method}</p>
                    {signal.evidence.map((line) => (
                      <p key={line} className="mt-2">
                        {line}
                      </p>
                    ))}
                    <p className="mt-2">{signal.invalidation_basis}</p>
                  </details>
                </section>
              ))}
            </div>
          </>
        ) : section === 'News report' ? (
          <>
            <ReportNarrative content={activeNarrative?.content} />
            {data.news || data.outlook?.news ? (
              <section className="mt-6 border-t border-neutral-800 pt-4">
                <h3 className="text-sm font-semibold">News sentiment</h3>
                <p className="mt-2 text-sm">
                  {(data.news || data.outlook!.news).summary.article_count}{' '}
                  articles · {(data.news || data.outlook!.news).summary.label}
                </p>
                <ul className="mt-3 space-y-2 text-sm">
                  {(data.news || data.outlook!.news).articles.map((article) => (
                    <li key={article.url}>
                      <a
                        className="underline underline-offset-4"
                        href={article.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {article.title}
                      </a>{' '}
                      · {article.source} ·{' '}
                      {new Date(article.published_at).toLocaleDateString()}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        ) : section === 'financial scores' ? (
          <>
            <div className="grid gap-6 sm:grid-cols-2">
              {quality ? (
                (
                  [
                    ['Quality', quality.quality],
                    ['Growth', quality.growth],
                  ] as const
                ).map(([label, score]) => (
                  <section key={label}>
                    <h3 className="text-lg font-semibold">
                      {label}: {num(score.score)}
                      <span className="text-xs font-normal text-neutral-500">
                        {' '}
                        / 100
                      </span>
                    </h3>
                    <p className="mt-1 text-xs text-neutral-500">
                      Unvalidated heuristic · {score.coverage_pct}% metric
                      coverage
                    </p>
                    {score.components.map((part) => (
                      <div key={part.name} className="mt-4">
                        <div className="flex justify-between gap-2 text-xs">
                          <span>
                            {part.name} ({Math.round(part.weight * 100)}%)
                          </span>
                          <span>{num(part.score)}</span>
                        </div>
                        <meter
                          className="mt-1 h-3 w-full"
                          min="0"
                          max="100"
                          value={part.score ?? 0}
                          aria-label={`${part.name}: ${part.score ?? 'unavailable'}`}
                        />
                        <p className="mt-1 text-xs text-neutral-500">
                          {part.method}
                        </p>
                      </div>
                    ))}
                  </section>
                ))
              ) : (
                <p className="text-sm">
                  Annual financial scores are unavailable.
                </p>
              )}
            </div>
            {quality ? (
              <>
                <dl className="mt-6 grid grid-cols-2 gap-4 border-y border-neutral-800 py-4 text-sm">
                  {Object.entries({
                    '3-year revenue CAGR %': quality.revenue_cagr_3y_pct,
                    '5-year revenue CAGR %': quality.revenue_cagr_5y_pct,
                    '3-year EPS CAGR %': quality.eps_cagr_3y_pct,
                    '5-year EPS CAGR %': quality.eps_cagr_5y_pct,
                  }).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-neutral-500">{label}</dt>
                      <dd className="mt-1 tabular-nums">{num(value)}</dd>
                    </div>
                  ))}
                </dl>
                <h3 className="mt-5 text-sm font-semibold">
                  Moat evidence: {quality.moat_label.replaceAll('_', ' ')}
                </h3>
                <ul className="mt-2 list-disc pl-4 text-sm">
                  {quality.moat_evidence.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                <details className="mt-4 text-xs text-neutral-500">
                  <summary className="cursor-pointer">
                    Score assumptions and coverage
                  </summary>
                  <ul className="mt-2 list-disc space-y-2 pl-4">
                    {quality.warnings.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </details>
              </>
            ) : null}
            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-xs">
                <thead>
                  <tr>
                    {[
                      'Fiscal date',
                      'Currency',
                      'Revenue',
                      'Net income',
                      'Free cash flow',
                      'EPS',
                      'Gross margin %',
                    ].map((label) => (
                      <th key={label} className="p-2 font-medium">
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {financials?.annual_financials?.map((row) => (
                    <tr
                      className="border-t border-neutral-800"
                      key={row.fiscal_date}
                    >
                      <td className="p-2">{row.fiscal_date}</td>
                      <td className="p-2">{row.currency ?? '-'}</td>
                      {[
                        row.revenue,
                        row.net_income,
                        row.free_cash_flow,
                        row.eps,
                        row.gross_margin_pct,
                      ].map((value, index) => (
                        <td key={index} className="p-2 tabular-nums">
                          {num(value)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <ReportNarrative content={activeNarrative?.content} />
        )}
        <DailyPatternsPanel
          key={`${report.id}:${report.updated_at}`}
          symbol={report.symbol}
          active={section === 'Daily patterns'}
        />
        {sectionCharts[section] ? (
          <Suspense
            fallback={<p className="py-6 text-sm">Loading charts...</p>}
          >
            <ResearchVisuals
              quote={data.quote}
              history={data.history}
              analysis={data.analysis}
              fundamentals={financials}
              outlook={data.outlook}
              news={data.news}
              view={sectionCharts[section]}
            />
          </Suspense>
        ) : null}
      </div>
      {[data.analysis_error, data.fundamentals_error, data.outlook_error]
        .filter(Boolean)
        .map((error) => (
          <p key={error} className="mt-4 text-sm text-amber-800">
            {error}
          </p>
        ))}
      {financials?.warnings.length ? (
        <details className="mt-5 text-xs text-neutral-500">
          <summary className="cursor-pointer">Provider notes</summary>
          <ul className="mt-2 list-disc space-y-2 pl-4">
            {financials.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  )
}

function ReportNarrative({ content }: { content?: string }) {
  return content ? (
    <div className="assistant-answer">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  ) : (
    <p className="text-sm text-neutral-500">
      This section is not available in this saved report. Refresh to generate
      the current report format.
    </p>
  )
}
