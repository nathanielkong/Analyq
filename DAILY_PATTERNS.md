# Daily Patterns: First Learning Checkpoint

## What exists now

GET `/stocks/NVDA/patterns?limit=100` returns deterministic daily observations.
Try it through `http://localhost:8000/docs` under stocks. A real request uses the
existing cached Alpaca history client, not Gemini. No new API key is needed.
This checkpoint is backend-only: it does not change chat, saved market analyses,
Market Watch, model training or predictions. No scheduled scans or alerts run.

Data flow:

`stocks.py route -> get_daily_patterns -> cached Alpaca adjusted history -> build_daily_patterns -> validated JSON`

## Files, in implementation order

1. `backend/app/api/schema/stock_patterns.py` defines the returned JSON fields.
   `DailyPatternCheck.detected` is true, false, or null when calculation is unavailable.
2. `backend/app/api/services/stock_analysis_services.py` exposes the existing RSI
   calculation as `calculate_rsi`. Its mathematical behavior is unchanged.
3. `backend/app/api/services/stock_pattern_services.py` collects history and performs
   the new calculations. `build_daily_patterns` itself makes no network requests.
4. `backend/app/api/routes/stocks.py` exposes the service through an HTTP endpoint.
   It validates the requested history size and maps provider failures to HTTP errors.
5. `backend/tests/test_stock_patterns.py` exercises calculations and the API using
   synthetic prices. Tests spend no provider credits.

The route handles HTTP; the service owns the calculations; the existing client owns
Alpaca requests. Keeping calculation separate from collection lets a later backtest
reuse the exact detector on historical prefixes rather than reimplement its rules.

## Definitions

Green/red below means higher/lower than the PREVIOUS CLOSE. A candle can close
above its own open but remain below yesterday's close. These are different facts.

### Daily return

`r[t] = (close[t] / close[t-1] - 1) * 100`

100 -> 104 is a +4% daily return. This alone does not establish a reversal setup.

### Signed streak

Count consecutive positive or negative returns, ending at the latest included bar.
100 -> 101 -> 102 -> 103 is +3. Four closes are needed for three changes.
A flat close or a change of direction breaks the streak. A value of -4 means four
successive declining observed closes. If the streak reaches the start of supplied
history, its actual length may be longer; `streak_reaches_history_start` marks this.

### RSI

Over the latest 14 price changes, average the gains and absolute losses separately.
`RS = average_gain / average_loss`; `RSI = 100 - 100 / (1 + RS)`.
No losses with positive gains gives 100; no gains or losses gives 50.
This reuses the application's SIMPLE-average RSI, not Wilder-smoothed RSI. It may
differ from a broker chart. A high RSI measures strong recent gains, not proof of
an imminent drop. At least 15 closes are needed.

### Unusually large daily move

Use the 20 returns BEFORE the latest return as a baseline:

`z[t] = (r[t] - mean(r[t-20:t])) / sample_std(r[t-20:t])`

The slice ends BEFORE t. Today must not change the baseline it is compared against.
With a prior average of 0% and standard deviation of 2 percentage points, a +6%
day has z = +3. A -6% day has z = -3. This needs 22 closes for 21 daily returns.
If prior variance is zero, z and its flags are unavailable, not infinity or zero.
This is a size measurement, not a probability; stock returns need not be normal.

## Four provisional rules

| Check | Definition |
| --- | --- |
| Rising streak/high RSI | Streak >= 3 and RSI > 70 |
| Falling streak/low RSI | Streak <= -3 and RSI < 30 |
| Unusually large up day | Return > 0 and z >= 2 |
| Unusually large down day | Return < 0 and z <= -2 |

These are hypotheses, not validated buy/sell rules. The cutoffs are explicit
starting choices, not fitted results or a claim of 90% accuracy.

## Data safeguards and limitations

- Requires adjusted daily prices. Unadjusted data gets no pattern flags.
- Excludes today's New York date and future dates, even after the close, matching
  the existing history client's conservative policy. This is not a live scanner.
- Rejects duplicate/out-of-order market dates and nonpositive/nonfinite closes.
- Withholds detection when the newest completed bar is over seven calendar days old.
  Seven days is a coarse guard, not verification that the latest exchange session exists.
- Counts observed bars, not calendar days. Missing exchange sessions are not verified;
  an exchange-calendar continuity check is required before reliable scheduled alerts.
- Carries provider warnings and the latest included timestamp. IEX data must not be
  silently treated as a consolidated all-exchange feed.
- Historical as-of filtering prevents future bars entering calculations, but today's
  adjusted history is not a point-in-time archive of what a provider published then.

## Next Checkpoint: Test Your Reversal Hypothesis

The first historical outcome study is now implemented at
`GET /stocks/{symbol}/patterns/backtest`. See [the backtest walkthrough](PATTERN_BACKTEST.md)
for its exact definitions, exclusions and limitations. The ideas below also include
future extensions, such as intraperiod excursions and regime-matched comparisons,
which are NOT yet part of that endpoint.

For each historical signal at t, examine return to closes t+1, t+3 and t+5.
Define the question precisely: lower final close is NOT the same as any intraperiod
dip, a 2% pullback, or a profitable trade after entry and costs.

For each rule/horizon report occurrence count, matured outcome count, reversal
frequency, confidence interval, mean/median forward return, and adverse/favorable
excursions. Compare against the unconditional outcome frequency on the same dates
and market regimes. Show missing outcomes, rather than counting unfinished labels
as losses. Handle overlapping events and test outside the threshold-development
period. A strategy simulation needs a feasible next entry (such as the next open),
fees, spread/slippage and gap risk; close-to-close hit rate is not tradable profit.

## Later: integrate with the direction model

The existing model is logistic regression, not linear price regression. Its labels
ask whether a later close is above today's close. It already has daily/5-day returns,
RSI, volatility, volume and benchmark features. Candidate additions are signed
streak, prior-baseline return z-score and explicit pattern interaction flags.

Compute these at each historical feature cutoff using only the available prefix.
Fit preprocessing on training folds only. Compare the old feature set against the
expanded set on identical chronological splits, including a gap for overlapping
multi-session labels. Measure baseline-relative performance, calibration, Brier
score and trading costs, not only accuracy. Adding features is not automatically
an improvement; do not force a reversal answer or manually assign 90% probability.

## Later: premarket/session divergence

Daily bars cannot reconstruct the premarket price path. We need timestamped
intraday data, verified feed/session coverage and an exchange calendar first.
Distinguish an overnight gap from movement WITHIN premarket:

- Gap at decision time: `(premarket_price / previous_regular_close - 1) * 100`.
- Premarket movement: `(latest_premarket_price / chosen_premarket_start_price - 1) * 100`.
- Regular-session move so far: `(price_now / regular_open - 1) * 100`.

A negative gap plus positive regular-session move describes a gap-down rebound;
a positive gap plus negative session move describes a gap-up fade. Choose meaningful
thresholds rather than labelling every tiny fluctuation a setup. A rebound from the
open can still leave the stock below yesterday's close.

At 09:29 New York time, the regular-session move is UNKNOWN. It may be a later
outcome label, never an input for that pre-open prediction. At 10:00, the first
30 minutes can be an input for a prediction AFTER 10:00, not a retroactive premarket
signal. Early closes, holidays, DST, stale trades and trading halts also matter.

## Verification

From backend: `.venv/bin/python -m pytest tests/test_stock_patterns.py -q`.
Then inspect the endpoint in Swagger. No live-price prediction or historical win
rate has been claimed or evaluated at this checkpoint.

Suggested commit: `feat: add descriptive daily stock pattern detector`
