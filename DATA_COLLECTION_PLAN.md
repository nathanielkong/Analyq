# Stock Research Data Collection Plan

## Objective

Build a traceable dataset before adding large numbers of indicators or predictive
models. Every collected value must record its source and observation time so a
model cannot accidentally use information that was unavailable at prediction time.

## Data Classes

The requested research features fall into three groups:

1. Raw provider data: prices, volume, statements, news, options, and macro data.
2. Derived features: returns, volatility, RSI, beta, P/E, and financial ratios.
3. Model outputs: next-day direction probabilities and price forecast intervals.

Derived features and model outputs should never be stored as if they were raw facts.

## Source Inventory

| Dataset | Preferred source | Status | Notes |
|---|---|---|---|
| Latest stock quote | Alpaca | Implemented | Current configured feed is IEX. |
| Adjusted daily OHLCV | Alpaca | Implemented | Split, dividend, and spin-off adjusted. |
| Benchmark OHLCV | Alpaca | Implemented | SPY is the initial default benchmark. |
| Intraday OHLCV | Alpaca | Planned | Needed for a genuine short-term mode. |
| Bid and ask quotes | Alpaca | Planned | Feed coverage depends on the account plan. |
| Company overview and ratios | Alpha Vantage | Planned | P/E, EPS, beta, market cap, and related fields. |
| Income statements | Alpha Vantage, then SEC verification | Planned | Annual and quarterly reports. |
| Balance sheets | Alpha Vantage, then SEC verification | Planned | Debt, cash, assets, and liabilities. |
| Cash-flow statements | Alpha Vantage, then SEC verification | Planned | Operating and investing cash flows. |
| Official filings | SEC EDGAR | Planned | No API key; useful for RAG and verification. |
| Earnings history/calendar | Alpha Vantage | Planned | Must preserve announcement timestamps. |
| Company news/sentiment | Alpha Vantage + VADER | Implemented baseline | Dated articles, provider score, local VADER score, deduplication, and temporary caching. |
| Corporate actions | Alpaca or SEC | Partly handled | Adjusted bars currently handle price continuity. |
| Macro series | FRED | Planned | Requires a separate API key. |
| Options chains and snapshots | Evaluate Alpaca plan | Research needed | Needed for IV, skew, open interest, and put/call. |
| Analyst targets/ratings | Provider evaluation | Source gap | Do not scrape sites without permission. |
| Short interest | Provider evaluation | Source gap | Frequency and licensing need review. |
| Social sentiment | Provider evaluation | Source gap | Requires quality and manipulation controls. |
| Full order book | Provider evaluation | Source gap | Not the same as a latest bid/ask quote. |

## Temporary Storage

The current checkpoint uses an in-process TTL cache:

- Latest quote TTL: 30 seconds.
- Adjusted daily history TTL: 15 minutes.
- Cache key includes provider, symbol, timeframe, bar count, completed market date,
  adjustment mode, and feed.
- Restarting FastAPI clears this cache.

This reduces duplicate provider calls while we are developing. It is not suitable
for model training because it is temporary and local to one backend process.

Later storage should be separated by purpose:

- PostgreSQL: provider metadata, fundamentals, news metadata, events, and model runs.
- Parquet/object storage: large historical price and feature datasets for ML.
- Redis, if justified later: shared short-lived production cache and request locking.

## Phase A: Price and Benchmark Dataset

Implemented inputs:

- Latest quote for the selected stock.
- Adjusted daily OHLCV for the selected stock.
- Adjusted daily OHLCV for SPY or another requested benchmark.
- Source, collection time, adjustment status, and data-quality warnings.

These inputs support later calculation of:

- Simple, log, rolling, and excess returns.
- Best/worst day and percentage of positive days.
- Volatility, downside deviation, drawdown, and Ulcer index.
- Beta, correlation, benchmark R-squared, and Jensen's alpha.
- Sharpe, Sortino, Calmar, Treynor, and information ratios.
- SMA, EMA, MACD, RSI, ATR, Bollinger Bands, momentum, and regression features.
- Volume, dollar-volume, OBV, and related daily liquidity approximations.

## Phase B: Fundamentals and Events

Collect annual and quarterly values with fiscal period and filing date. Required
inputs include revenue, gross profit, operating income, net income, EPS, assets,
liabilities, debt, cash, operating cash flow, capital expenditure, shares
outstanding, dividends, and earnings dates.

These inputs support later calculation of:

- P/E, P/S, P/B, EV/EBITDA, EV/Sales, and P/FCF.
- FCF yield, earnings yield, dividend yield, and payout coverage.
- Gross, operating, and net margins.
- ROE, ROA, ROIC, and DuPont analysis.
- Revenue, EPS, and FCF growth.
- Debt ratios, interest coverage, liquidity ratios, and financial-health scores.

Calculated ratios must use values from compatible fiscal periods. A current price
must not be combined blindly with stale or mismatched statement periods.

## Phase C: News and Sentiment

Store each article's provider, source, URL, title, publication timestamp, ticker
relevance, topics, raw sentiment, and fetch timestamp. Deduplicate by canonical URL
or a content fingerprint.

The first sentiment feature should aggregate only articles published before the
analysis timestamp. This prevents future news from leaking into backtests.

Implemented baseline:

- Alpha Vantage `NEWS_SENTIMENT` collection over a requested date window.
- Typed parsing of titles, summaries, URLs, sources, topics, publication times,
  symbol relevance, and symbol-specific provider sentiment.
- URL deduplication and a 15-minute in-process cache.
- A minimum symbol-relevance filter so secondary ticker mentions do not dominate
  the selected company's sentiment.
- Local VADER scores for each headline plus summary.
- Relevance-weighted aggregate sentiment and positive/neutral/negative counts.
- Explicit requested-window and returned-article coverage timestamps.

Alpha Vantage can cap a popular symbol at 1,000 articles. When this happens, the
returned articles may cover only the newest part of the requested period. The
direction model must not treat unreturned older dates as days with zero news.

## Phase D: Short-Term Direction Model

The initial target should be classification, not a certain prediction:

`P(next completed close is higher than today's completed close)`

The output should look like:

- Up probability: 0.57
- Down probability: 0.43
- Confidence: low
- Model version and training window
- Features and data timestamp

Required safeguards:

- Start with a naive baseline and logistic regression.
- Use chronological walk-forward validation.
- Fit scalers and feature transformations on training data only.
- Include transaction costs and turnover in any trading backtest.
- Report directional accuracy, calibration, and information coefficient.
- Never describe a probability as certainty or financial advice.

Implemented baseline:

- Regularized scikit-learn logistic regression in a scaler/model pipeline.
- One-day, five-day, intraday, range, volatility, moving-average, RSI, ATR,
  volume, benchmark, and excess-return features.
- News sentiment/count features only when the requested historical period is
  complete enough to align safely; otherwise the response explicitly reports a
  price/volume/benchmark fallback.
- Chronological `TimeSeriesSplit` validation, majority-class baseline accuracy,
  one-day momentum and SPY-direction baselines.
- Accuracy, balanced accuracy, precision, recall, F1, ROC AUC, Brier score, log
  loss, confusion counts, calibration bins, fold results, decisive-prediction
  coverage, and standardized coefficient stability.
- Stronger L2 regularization (`C=0.1`) after the first cross-symbol audit showed
  that version 1.0 probabilities were too extreme.
- A provisional validation gate. A directional lean is shown only when the model
  beats the strongest naive accuracy baseline by at least two percentage points,
  reaches ROC AUC 0.52, and improves on the historical-up-rate Brier baseline.
  Otherwise the user-facing result is `mixed` with an explicit status.
- Target: whether the next completed adjusted daily close is above the current
  completed adjusted daily close.

## Phase E: Price Forecast

Price forecasting comes after the direction baseline. It should return a range and
uncertainty, not one authoritative future price. Evaluate it against simple
baselines such as the latest close, drift, and moving average using MAE and RMSE.

Complex models such as gradient boosting, GARCH, LSTM, transformers, and hidden
Markov models should only be added when they beat simpler walk-forward baselines.

## Immediate Next Checkpoint

Add Alpha Vantage fundamentals collection with temporary caching and a typed API
response. Begin with company overview, income statement, balance sheet, cash flow,
and earnings. Do not calculate every ratio until the raw fields and fiscal dates
have validation and tests.
