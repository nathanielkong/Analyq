# Daily Pattern Backtesting: Second Learning Checkpoint

## Try it

With the backend running, open `http://localhost:8000/docs`, expand
`GET /stocks/{symbol}/patterns/backtest`, select Try it out, enter a ticker, and Execute.

Direct example: `http://localhost:8000/stocks/NVDA/patterns/backtest?limit=250`.

The endpoint requests up to 250 adjusted daily bars through the existing cached
Alpaca client. That is roughly one trading year, NOT a two-year study. Missing bars
or a short listing history can reduce the sample. Provider calls can use your quota;
there are no Gemini calls, no new keys, no database writes, and no model retraining.
Tests use synthetic data rather than your provider account.

In the frontend, open a saved stock's Market analysis and select **Daily patterns**.
The first selection loads the study; changing horizons or leaving and returning to
the section reuses that result while the report remains mounted. The refresh icon
requests it again (the provider's history cache can still apply). Switching reports,
refreshing the saved report or reloading the page can load a new study.

This is a separately fetched study, not part of the saved daily report snapshot.
Its own observation dates and fetch time are displayed. It is not yet supplied to
chat narration or used by Market Watch or the regression model.

## What question are we answering?

After an upward pattern, was the closing price LOWER 1, 3 or 5 observed bars later?
After a downward pattern, was it HIGHER?

`forward_return_pct = (future_close / signal_close - 1) * 100`

For example, if a rising-streak pattern is detected at a close of 100 and the close
three bars later is 97, the forward return is -3% and the reversal condition is true.
If the stock dips to 95 first but ends at 102, it is NOT a three-bar final-close
reversal. An intraperiod dip, a drawdown threshold and a profitable executed trade
are separate questions. The returned mean/median returns are the STOCK's signed
returns, not the profit from shorting it or buying it.

## Follow one request through the files

1. `backend/app/api/routes/stocks.py`: validates the ticker/history-limit request,
   calls the service and maps provider errors to HTTP responses.
2. `backend/app/api/services/pattern_backtest_services.py`:
   `get_daily_pattern_backtest` fetches history once; `build_daily_pattern_backtest`
   performs the historical study. These are separate so tests need no network.
3. `backend/app/api/services/stock_pattern_services.py`: the EXISTING detector is
   called with one historical prefix at a time. The new service does not copy or
   change its RSI, streak or unusually-large-move rules.
4. `backend/app/api/schema/pattern_backtest.py`: defines the structured results,
   baseline, sample accounting and individual dated observations.
5. `backend/tests/test_pattern_backtest.py`: tests hand-calculated examples,
   information cutoffs, missing outcomes, overlaps, uncertainty and API behavior.
6. `frontend/src/api/patterns.ts`: requests the study when its tab is selected.
   `frontend/src/types/patterns.ts` describes the response for TypeScript.
7. `frontend/src/components/DailyPatternsPanel.tsx`: manages loading, retry and
   refresh, then displays the latest checks, rate bars, samples and dated evidence.
   Horizon selection only changes which returned numbers are displayed.
8. `frontend/src/components/SavedResearchReport.tsx`: places that panel inside
   the existing report sections without generating another LLM report.

The response includes `latest_patterns` from the same history used for the study.
The frontend does not need a second detector request or recalculate the statistics.

The existing pattern schema now exports its pattern-name type for both responses;
the date parser is shared so the detector and backtest use the same New York cutoff.

## How we avoid looking into the future

First, validate the history and exclude today's New York bar and any future bars.
This deliberately matches the detector's conservative completed-day policy.

For historical index t, call the detector using ONLY bars 0 through t. Its clock
is set to the next New York midnight so t is eligible as a completed observation.
Prices after t never enter that detection. Only after obtaining the pattern flags
do we inspect later closes to measure the outcome.

This is a historical description, not an executable entry at t's closing price:
the complete closing bar is only known after that close. A trading backtest would
need a feasible subsequent fill and would measure returns from that fill.

## Which events count?

- Only a known false-to-true transition starts a new event. An ongoing five-day
  occurrence of the same rule is not counted as five separate starts.
- If a pattern is already true when enough history first becomes available, its
  actual start is unknown. `initial_active_excluded` counts those excluded starts.
  The same exclusion applies when a check becomes known again after an unknown state.
- Each horizon independently excludes overlapping measured windows for a pattern.
  If an accepted event is at bar 20 with a five-bar horizon, a new event at bar 23
  is excluded; an event at 25 is permitted. Different horizons can have different counts.
- Events with no final close yet are `pending_outcomes`, never automatic losses.
- A flat final return stays in the denominator but is not a reversal.

For each horizon: `signal_count = pattern.count + pending_outcomes + overlap_excluded`.
Initially-active exclusions are separate because their start was not established.
Pending classification takes precedence while an event's outcome is unfinished.

## Read the output

Each of four pattern results contains three horizon summaries:

| Field | Meaning |
| --- | --- |
| `horizon_bars` | 1, 3 or 5 later supplied daily observations |
| `pattern.count` | Completed, non-overlapping measured events |
| `pattern.reversals` | Events ending in the specified opposite direction |
| `pattern.reversal_rate_pct` | Reversals divided by measured events, times 100 |
| `pattern.mean_return_pct` | Average signed stock return after events |
| `pattern.median_return_pct` | Middle signed stock return after events |
| `baseline` | Same outcome metrics over all dates where that rule was evaluable |
| `reversal_rate_difference_pp` | Pattern rate minus baseline rate, in percentage points |
| `approximate_wilson_95_*` | Approximate uncertainty bounds for the observed reversal proportion |
| `outcomes` | Dated individual observations so you can audit the summary |

The baseline includes signal dates and uses the same cutoff/horizon; its windows
can overlap. It is an unconditional reference, not a control group matched by
market regime, liquidity or volatility. A positive rate difference is not evidence
of statistical significance or causality.

If there are no measured events, rates/means/intervals are null, not 0%. Fewer than
30 events is marked `small_sample`; larger samples are still only `descriptive_only`.
Thirty is a display caution threshold, not a test proving a predictive advantage.

The Wilson bounds use a binomial approximation. For 5 reversals in 10 observations,
the observed rate is 50%, with approximate bounds of 23.7%-76.3%. This illustrates
sampling uncertainty, not a 95% chance that the next trade wins. Even after excluding
overlaps, market observations may remain correlated, making those bounds too narrow.

## What this does NOT prove

No out-of-sample performance, tradable win rate, net profits, or guaranteed next-day
direction. The cutoffs were not optimized, but repeated experimentation on the same
history would still overfit it. A future model comparison needs held-out chronological
periods, multiple market regimes and suitable gaps for multi-bar targets.

Missing exchange sessions, feed coverage and historical corporate-action adjustment
vintages are not independently verified. Horizons count the supplied bars. An old
dataset can be studied historically even when it is too stale for current detection;
the data-through timestamp and inherited staleness warnings remain visible.

We do not simulate intraday excursions, order fills, short-sale costs, fees, spreads,
slippage or separate dividend cash flows. Premarket/session divergence still needs
intraday data and an explicit decision-time definition.

## Your next learning task

Inspect one stock's rising-streak result. Look at sample count FIRST, then the
three-bar reversal rate and its unconditional baseline. Ask: does the pattern tell
us something beyond what happens on ordinary dates? A tiny sample means "unknown",
not "the model is broken" and not "the stock always reverses".

Use the frontend evidence table to inspect individual dated outcomes. Adding
features to logistic regression comes after this inspection and a proper
old-versus-new model validation plan, not before it.

Run tests from backend:
`.venv/bin/python -m pytest tests/test_pattern_backtest.py -q`

Frontend browser checks cover loading, cached tab revisits, horizon changes,
zero-event results, errors and retry, stale/empty data, and desktop/mobile layout.
They use synthetic responses, not paid market-data or LLM calls.

Suggested commit: `feat: show daily pattern evidence in market analysis`
