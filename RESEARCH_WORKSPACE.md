# Saved Research Workspace

## What Changed

The current UI uses `POST /assistant/chat`. A chat has one persistent PostgreSQL
`research_reports` row per resolved stock symbol, enforced by a unique constraint.
Messages reference report IDs rather than repeating the full research JSON.
The original `/assistant/research` endpoint remains available for compatibility.

- First single-stock question (including entry-price questions): collect a full
  stock snapshot and write one standalone market analysis. Return the user's direct
  answer separately. The UI keeps the Chat tab active and links to the report.
- Later questions on the same calendar day: interpret intent, select relevant evidence from the saved
  snapshot, and generate only a focused chat answer. Do not recollect prices,
  fundamentals/news, retrain the direction models, or regenerate the report.
- New stock: create another report tab within the same chat.
- Comparison: reuse available reports; collect only the requested evidence plus
  fundamentals for other companies. Return comparison text and a metrics table
  in chat, without creating report tabs. Only an explicit request for separate
  market analyses creates reports for the selected companies (up to five).
  Asking for a detailed comparison alone does not request separate reports.
- General finance concepts: answer in chat without market-data collection.
- Refresh: explicitly recollect/recalculate and replace the same report. Existing
  provider caches still apply (quotes 30 seconds, history/news 15 minutes, complete
  fundamentals 24 hours). Report timestamps and underlying observation dates are
  distinct; a saved snapshot is never a guarantee of live data.

## Daily Reports and Section Tabs

The Broadcom example is a structural reference, not a source of market facts or
instructions. New reports contain an executive overview and eight sections:
Market report, Market outlook, Fundamentals, Sentiment report, News report,
Bull and bear case, Investment plan, and Risk management. Each evidence-rich section
targets 180-280 useful words, with shorter explanations when data is unavailable.
Existing price/volume charts, model probability bars, valuation metrics, sentiment
bars, and financial-score meters remain alongside the relevant sections.

`daily_research_cache` stores one reusable snapshot per signed-in account and
resolved symbol. Another chat within that account attaches a copy without collecting
data or generating another market analysis. It preserves the original generation time and
expiry. Guests are isolated by chat; no private reports are shared across accounts.

Expiry is the next **calendar midnight** in `REPORT_TIMEZONE`, default
`Australia/Melbourne`, not 24 hours after creation. A report created at 23:59 has one
minute of remaining reuse. DST transitions use the actual next local midnight.
Every new question checks freshness, including in an existing chat. Expired reports
are replaced on the next stock question; opening an old chat alone does not spend
credits. Its historical snapshot remains visible and marked archived. This is a
reuse policy, not automatic deletion of the user's research history.

Expired cache rows are removed lazily on the account's next report request; idle
accounts have no scheduled cleanup job. A new snapshot overwrites the symbol's cache
row. Format-version changes also invalidate reuse. Provider cache keys include the
report date, so yesterday's cached fetch is not relabelled as today's fetch. Fresh
requests can still return the same latest closing price or fiscal statement if the
provider has not published anything newer. Observation dates remain visible.

Manual refresh replaces the daily cache too, and other chats adopt that replacement
on their next relevant question. Same-day provider TTLs still apply. Reports first
requested before midnight retain their collection date even if narration finishes
after midnight. They are not silently promoted to the next day's research.

`report_policy.py` defines the calendar, expiry, format version and section names.
`daily_report_cache.py` handles reuse and a PostgreSQL transaction-scoped advisory
lock per account, preventing simultaneous chats from generating the same report.
Migration `0004_daily_research_cache` adds the cache table and report expiry/version.
The original session lock still protects message ordering and idempotent retries.

Each new report receives a 9,000-token output allowance in the combined call.
Explicit multi-report requests increase that allowance per report needing narration;
cached reports do not. Follow-ups use a 3,000-token budget and focused evidence.
All eight sections come from **one** narration call, not eight agent calls. The
bull/bear section is an evidence comparison, not a claim that separate agents debated.
News context includes at most ten supplied summaries, each capped at 1,000 characters;
it does not pretend that social feeds, filings or full articles were retrieved.

Follow-ups still consume Gemini tokens: one interpretation call and one concise
answer call. A new report uses one combined answer/report generation call, not
one narration call for every section. "Collect once" means once per stock report,
not one HTTP request across every market-data endpoint.

## Responsibilities and Data Flow

### Daily Pattern Evidence

The **Daily patterns** report section independently loads
`GET /stocks/{symbol}/patterns/backtest?limit=250` on first selection. It shows
latest completed-bar detections and historical 1/3/5-bar reversal rates against
an unconditional baseline, with sample counts, approximate uncertainty bounds
and dated outcomes. Its timestamps are separate from the saved report snapshot.
Tab/horizon changes reuse the mounted panel's response; refresh can request fresh
data, subject to provider caching. No LLM call or model retraining is performed.
These results are not currently included in chat narration. See
`PATTERN_BACKTEST.md` for definitions and limitations.

### Research Flow

`assistant.py` route -> `research_report_services.py` orchestration -> existing
market-data collectors -> deterministic analytics -> Gemini narration -> DB commit.

- `models/research_report.py`, migration `0003_saved_research_reports`: durable
  snapshots belonging to a chat; deletion cascades with the chat.
- `research_report_services.py`: ownership checks, report reuse, evidence selection,
  comparisons, narrative generation, message persistence and idempotent retries.
- `financial_quality_services.py`: annual statement alignment, growth, transparent
  quality/growth composites and quantitative moat proxies.
- `peer_comparison_services.py`: side-by-side metrics and user-selectable weights.
- `horizon_signal_services.py`: keeps next-close/3-session/5-session model results,
  weeks-to-months technical conditions, and years-out fundamentals separate.
- `SavedResearchReport.tsx`: report tabs, report sections, financial score details,
  annual table and existing charts. `App.tsx` retains the chat and saved-session UI.
- Stock comparison/ranking tables appear in chat. Market Watch contains movers
  and news catalysts, not a watchlist ranking form.

The backend locks the chat session during a request. Reusing the same request UUID
replays the stored turn. Different concurrent requests are serialized, preventing
duplicate report creation. This simple local-app approach holds a database
connection during research; a job queue is preferable at higher concurrency.

## Financial Data and Scores

Alpha Vantage OVERVIEW, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW and EARNINGS
provide the current overview and up to six annual observations (six observations
are needed for a five-year growth calculation). Balance/cash payloads are reused
within collection instead of requesting each once for current data and again for
annual history. Successfully completed fundamentals are cached for up to 24 hours,
with a new cache key on each report date;
partial/error results are not cached for a whole day.

Statements are matched by exact fiscal date. Cash flow and balance-sheet amounts
with mismatched reporting currencies are excluded. NaN, infinity and missing
provider values become unavailable, not zero. CAGR requires positive endpoints,
consecutive annual observations and the same currency.

Quality weights are 25% each:

| Dimension | Formula |
| --- | --- |
| Profitability | Mean of annual net margin /20%, ROE /20%, ROA /10%, each clipped to 0-100 |
| Balance sheet | Mean of debt/equity scaled from 2 (0 points) to 0 (100), and current ratio from 0.5 to 2 |
| Cash generation | Mean of FCF margin /20% and operating cash flow/net income /1 |
| Consistency | Percentage of last three annual observations with positive profit AND FCF |

Growth weights are 25% each: three-year revenue CAGR scaled 0-20%; three-year
reported EPS CAGR scaled 0-20%; three-year operating-margin change scaled -5 to +5
percentage points; and percentage of valid annual transitions with revenue growth.
Missing dimensions prevent a composite score; weights are not silently reassigned.
Financial and real-estate sectors are excluded from these industrial-company scores.

ROE/ROA use year-end balances, not average balances. Reported EPS may require split
and restatement checks. Scores are NOT validated return predictors or probabilities.
No historical high-score-cohort backtest is claimed: it needs point-in-time filings,
publication dates, historical membership/delistings and out-of-sample evaluation.

Moat proxies report gross-margin level/stability and ROE persistence. They are
labelled supportive/mixed/insufficient evidence, not a falsely precise moat number.
Gemini can discuss the supplied company description and linked news, but has not
retrieved SEC filings or proven a wide/narrow moat from general model knowledge.

## Comparisons and Ranking

Chat comparisons call the peer comparison service and display its table with the
answer. The user can request a value, growth or quality focus in their message.
The compatibility endpoint `POST /market/rank` remains available, but has no Market
Watch control. Peers are user-supplied, not guessed automatically.

The interpreter's `report_queries` list is empty for ordinary comparisons. An
explicit request can select all compared stocks or just a subset; identities must
also appear in `stock_queries`. The service resolves aliases, reuses same-day saved
reports, and creates only selected report tabs. A later comparison does not inherit
permission to generate individual reports from an earlier message.

| Preset | Value | Quality | Growth |
| --- | --- | --- | --- |
| Value | 60% | 25% | 15% |
| Quality | 20% | 60% | 20% |
| Growth | 15% | 25% | 60% |

Value score rescales the existing valuation votes to 0-100: `50 + 50*score/count`,
requiring at least two metrics. All three component scores are required to rank.
Ties share rank. The table retains reporting dates and warns about sector/period
mismatches rather than claiming every company's fiscal periods match.

Sales/growth = trailing P/S divided by quarterly revenue YoY growth in percentage
points (20 for 20%). Zero/negative growth produces no ratio. Forward P/S is unavailable
without forward revenue estimates. P/FCF uses annual FCF, not TTM FCF. These ratios
are comparison heuristics, not intrinsic-value calculations.

## Horizons and Entry Plans

The logistic-regression service now fits separate 1/3/5-session targets using the
same collected data. A target compares the close N observations ahead with the
current close. The final N rows have unknown labels. Chronological validation
purges N training rows before each validation fold, and fits preprocessing only
on training data. Each horizon has its own baseline, probability and validation.
Multi-session validation labels overlap, so observations are not independent.

Weeks-to-months: descriptive 20/50-day moving-average trend with RSI context.
Years: favorable requires quality >=65, growth >=60 and lower/balanced valuation;
caution if quality <40, growth <35 or unprofitable; otherwise mixed. Missing inputs
produce insufficient data. This is an explicitly unvalidated fundamental stance.

ATR buy-in zones remain technical reference ranges, not DCF fair values. The
long-term view instead uses business-thesis review conditions (cash generation,
growth, leverage and valuation), not a 50-day low as a long-term stop loss.

## Verification

From `backend`: `.venv/bin/python -m pytest -q`.
Opt-in isolated PostgreSQL concurrency test:
`ANALYQ_POSTGRES_TEST=1 .venv/bin/python -m pytest tests/test_report_postgres.py -q`.
It creates and removes only its own unique test schema.

From `frontend`: `npm run build` and `npm run lint`.

Browser smoke test uses synthetic data and no paid APIs. Start from `backend`:
`PYTHONPATH=.:tests .venv/bin/python tests/report_ui_server.py`.
With frontend Vite running, run `node tests/report-workspace.smoke.cjs` from
`frontend` using an installed Playwright module (or set `PLAYWRIGHT_MODULE` to its
path). It defaults to an installed Chrome and writes screenshots under `artifacts/`.
Also run `node tests/chat-controls.smoke.cjs` against that fixture to check password
accounts, inline charts, stop generation and scroll controls on desktop/mobile.

## Conversational Answers and Funds

Chat answers have no generated title or "Direct answer" heading. The Gemini prompt
asks for the actual answer first, acknowledges concerns the user explicitly voices,
and avoids repeating earlier indicator summaries. Length follows the question,
with up to 3,000 output tokens for a follow-up; this is a ceiling, not a target.
Factual numbers must still come from the supplied evidence. No sample answer's
market claims, prices or sources have been copied into the application.

The model may select up to two existing price, fundamentals, news or model charts.
The backend stores the chosen chart inputs with that chat turn so refreshing a
report does not silently change an old answer's chart. Charts are deterministic
frontend renderings, not LLM-generated numbers.

`instrument_services.py` detects funds from the provider's instrument type/name.
Recognized ETFs/ETNs skip company financial statements: missing corporate revenue,
earnings or balance sheets are not a fund failure. Fund holdings, fees, NAV and
issuer documents are still not collected. Price/volume and other available
research remain usable. Detection depends on the provider's metadata; it is not a
complete security master. Report format version 3 refreshes old-format cached
reports on the next relevant question, rather than rewriting chat history.

## Stop Generation

The browser aborts its pending fetch and sends a cancel request with the same
session and request UUID. `generation_requests` stores cancellation in PostgreSQL
so all API workers can see it. Research checks cancellation between major stages
and before committing the report/messages. Cancelled work rolls back.

Completion and cancellation serialize on the request row. If completion wins,
the UI retrieves the saved answer and explains that it had already finished.
If cancellation wins, the question returns to the composer for editing/retry.
An already-running provider HTTP call may finish and be billed; this is cooperative
cancellation, not a promise to reverse consumed API tokens. If the cancel request
fails, the UI explicitly says the backend stop could not be confirmed.

The jump-to-latest arrow appears when the chat is scrolled up. New messages do
not pull the user down while they are reading earlier content.

## Password Accounts

`LoginDialog.tsx` sends credentials to `/auth/register` or `/auth/login` over the
existing API client. The route validates input; `password_auth.py` hashes/verifies
with Argon2id; PostgreSQL stores only the encoded hash. Successful login sets the
same HttpOnly session cookie as Google login. Credentials are never placed in
localStorage or returned in API responses, including validation failures.

Usernames are case-insensitive, 3-32 ASCII letters/digits/underscores. Registration
requires a 15-128 character passphrase. Set a strong `AUTH_SESSION_SECRET` to enable
password accounts. Existing Google accounts remain intact; a new username account
is separate, not an automatic link to a Google account or its chat history.
Password recovery, verified email and account linking are not implemented yet.

Migrations `0005_password_accounts` and `0006_generation_control` add nullable
username/hash fields and request-control records. Run `alembic upgrade head` on
other environments before starting the updated backend. Install backend dependencies
again after pulling this change because Argon2 is a new dependency.

## Hosting Choices

These are planning options, not deployed resources. Checked 25 September 2026.

| Option | Suggested use | Trade-off |
| --- | --- | --- |
| Railway | First small hosted demo: API plus PostgreSQL, with a frontend service | Simple platform workflow; usage-based costs need limits. Hobby starts at $5/month including $5 usage, not a guarantee the whole app costs $5. |
| Render | Static frontend, Python web service and PostgreSQL | Convenient managed services. Free tiers are suitable for experiments, not durable production assumptions; check sleep/storage/expiry limits. |
| AWS Lightsail | Docker/Linux deployment to learn AWS operations | More control and learning, but you own patching, TLS/reverse proxy, monitoring and backup configuration. |

Sources: [Railway plans](https://docs.railway.com/pricing/plans),
[Render free-tier limitations](https://render.com/docs/free),
[Lightsail pricing](https://aws.amazon.com/lightsail/pricing/).
My recommendation is Railway for the first demo; Lightsail later if AWS operations
are the next learning objective. LLM/market-data fees, domain and backups are separate
budget considerations. Measure memory during sklearn inference/training before
choosing an instance; the smallest tier is not automatically sufficient.

Before a public launch:
- Require authentication and per-account quotas on paid research/API routes; guest
  access is currently a local-development convenience, not public tenant isolation.
- Replace the process-local login throttle with a shared gateway/Redis limiter,
  configure trusted proxies, and add password recovery/verified contact details.
- Use HTTPS, `AUTH_COOKIE_SECURE=true`, a strong session secret and restricted CORS.
- Prefer one origin through a reverse proxy, or properly configured same-site
  custom domains. Unrelated frontend/API hosting domains conflict with the current
  SameSite=Lax cookie. Do not switch to cross-site cookies without CSRF protection.
- Put PostgreSQL on persistent storage with tested backups and migrations; do not
  expose the database publicly using local default credentials.
- Keep provider secrets server-side; add usage budgets, logs and monitoring.
- Confirm provider permissions for displaying/redistributing market data before
  exposing it to other users. Having an API key alone is not redistribution approval.

Response style is prompt engineering, not model fine-tuning. Synthetic tests prove
the contracts and UI work, not that every live model answer will be empathetic or
financially correct. A small real-prompt evaluation is the next quality checkpoint.

## Gemini Failures and Retry

The expanded chat/report response schema was reproduced returning HTTP 400
`Invalid argument`, while a minimal schema worked with the same key and model.
Removing nested string/array length bounds from the provider schema made the full
schema acceptable. `chat_response_schema` now sends that simplified schema; ordinary
follow-ups omit report definitions entirely. Pydantic still enforces all original
length limits, the five-report cap, eight ordered report sections and requested
symbols when parsing the response. This changes only the provider-facing format,
not stored data or API validation. A live follow-up check also passed after the fix.
Google notes that [large or deeply nested schemas may be rejected](https://ai.google.dev/gemini-api/docs/structured-output).

The old "Gemini could not interpret the prompt" message represented any upstream
API error during intent extraction, not necessarily an ambiguous question. The
client now maps quota, access/configuration, network and timeout failures to distinct
messages. Assistant routes preserve the mapped 429/503/504 status. Diagnostic logs
record operation, HTTP code and attempt, never the prompt, API key or raw provider
error payload. Historical errors without those diagnostics cannot be diagnosed
retroactively from the generic message alone.

Explicit 500/502/503 responses receive one retry after a short jittered delay;
SDK retries are disabled to avoid multiplying attempts. No automatic retry for
quota/billing, credentials, malformed requests, or network timeouts. A provider
call has a 90-second timeout. A retry can still incur provider usage; it is bounded,
not a guarantee of no duplicate billing. See [Google's troubleshooting guidance](https://ai.google.dev/gemini-api/docs/troubleshooting).

The chat Retry button reuses the same question, chat, report context and request
UUID. Existing idempotency checks prevent a saved turn from being duplicated.
It does not replace failed research with guessed facts. Premarket/opening questions
are valid requests, but daily-bar evidence cannot establish an intraday price path.

## Provider References

- [Alpha Vantage fundamental endpoints](https://www.alphavantage.co/documentation/#income-statement)
- [Alpaca snapshots](https://docs.alpaca.markets/us/reference/stocksnapshots-1)

The quote service now uses Alpaca snapshots to populate previous close and price
change when available, rather than leaving those fields empty on every quote.

## Deliberately Not Claimed

- A point-in-time cohort backtest proving quality/growth scores predict returns.
- Guaranteed returns, exact future prices, or an intrinsic-value entry price.
- Forward revenue estimates, automatic peer selection, filing retrieval or RAG.
- A market-wide ranking: the screener evaluates only the supplied 2-5 stocks.
