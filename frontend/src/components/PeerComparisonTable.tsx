import type { PeerComparison } from '../types/financialQuality'

const display = (value: number | null) =>
  value == null ? '-' : value.toFixed(2)

export function PeerComparisonTable({
  comparison,
}: {
  comparison: PeerComparison
}) {
  return (
    <section className="mt-5 min-w-0 border-t border-neutral-800 pt-4">
      <h4 className="text-sm font-semibold">
        Peer comparison · {comparison.preset}
      </h4>
      <p className="mt-1 text-xs text-neutral-500">
        {Object.entries(comparison.weights)
          .map(([name, weight]) => `${name} ${Math.round(weight * 100)}%`)
          .join(' / ')}{' '}
        · Unvalidated heuristic
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead>
            <tr>
              {[
                'Stock / fiscal period',
                'Rank',
                'P/S TTM',
                'P/FCF annual',
                'EV/EBITDA',
                'Gross margin %',
                'Revenue YoY %',
                'Sales/growth',
                'Quality',
                'Growth',
                'Weighted',
              ].map((label) => (
                <th key={label} className="p-2 font-medium">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.rows.map((row) => (
              <tr key={row.symbol} className="border-t border-neutral-800">
                <td className="p-2">
                  <strong>{row.symbol}</strong>
                  <br />
                  {row.fiscal_date ?? 'Unknown period'}
                </td>
                {[
                  row.rank,
                  row.price_sales_ttm,
                  row.price_fcf_annual,
                  row.ev_ebitda,
                  row.gross_margin_pct,
                  row.quarterly_revenue_growth_yoy_pct,
                  row.sales_growth_multiple,
                  row.quality_score,
                  row.growth_score,
                  row.weighted_score,
                ].map((value, index) => (
                  <td key={index} className="p-2 tabular-nums">
                    {display(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="mt-3 text-xs text-neutral-500">
        <summary className="cursor-pointer">Methods and data gaps</summary>
        <ul className="mt-2 list-disc space-y-2 pl-4">
          {comparison.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </details>
    </section>
  )
}
