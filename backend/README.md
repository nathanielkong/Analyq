# Analyq Backend

FastAPI backend for Analyq.

## Local Setup

From the `backend` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run The API

```bash
uvicorn app.main:app --reload
```

Health check:

```text
http://localhost:8000/health
```

Stock quote check:

```text
http://localhost:8000/stocks/NVDA
```

Daily pattern checks (backend-only, no LLM or prediction):

```text
http://localhost:8000/stocks/NVDA/patterns?limit=100
```

See [the daily-pattern walkthrough](../DAILY_PATTERNS.md) for formulas, data
limitations and the planned backtesting step.

Historical pattern outcomes at 1, 3 and 5 observed daily bars:

```text
http://localhost:8000/stocks/NVDA/patterns/backtest?limit=250
```

See [the backtesting walkthrough](../PATTERN_BACKTEST.md) for sample accounting,
baseline comparisons and why these descriptive results are not a trading win rate.

## Environment Variables

Create `backend/.env` locally and add:

```bash
MARKET_DATA_PROVIDER=alpaca
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_DATA_FEED=iex
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.1-flash-lite
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/stock_intelligence
GOOGLE_CLIENT_ID=your-google-web-client-id.apps.googleusercontent.com
AUTH_SESSION_SECRET=replace-with-a-long-random-value
AUTH_COOKIE_SECURE=false
```

Do not commit real API keys. The browser never receives these values; FastAPI reads
them from `backend/.env` and calls the providers on the server.

## Google Sign-In

Create a Google Cloud **Web application** OAuth client and add this authorized
JavaScript origin for local development:

```text
http://localhost:5173
```

Put the generated client ID in `backend/.env` as `GOOGLE_CLIENT_ID`. The frontend
loads that public client ID from `GET /auth/config`; the client secret is not needed
for the Google Identity Services ID-token flow. FastAPI verifies the returned token,
stores the user in PostgreSQL, and creates a signed HttpOnly application session.

Generate a local session secret with:

```bash
openssl rand -hex 32
```

Keep `AUTH_COOKIE_SECURE=false` on local HTTP. Set it to `true` behind HTTPS in
production.

To switch back to Alpha Vantage for comparison:

```bash
MARKET_DATA_PROVIDER=alpha_vantage
MARKET_DATA_API_KEY=your_alpha_vantage_key
```

## Interpret A Research Prompt

Send natural-language stock research requests to:

```text
POST http://localhost:8000/assistant/research
```

Example body:

```json
{
  "message": "Which price is a good price to buy in?",
  "session_id": "a-chat-session-uuid"
}
```

`session_id` is optional for a new standalone request. For a follow-up question,
send the active chat session ID so the backend can provide Gemini with a small
window of recent messages and the last verified stock symbol. The backend still
resolves and validates that symbol before requesting market data.

Gemini converts the sentence into validated structured fields such as the company,
time horizon, and requested data. The assistant service then resolves the company
and calls only the required market-data functions. A second Gemini call receives a
compact package of those verified results and returns a Markdown overview plus
optional question-specific sections. The frontend displays those sections as tabs.
Gemini does not calculate prices or choose which backend code is allowed to run.

The first version supports one company per request. Stock comparisons, citations to
retrieved documents, and RAG are intentionally deferred.

## Run PostgreSQL

From the project root:

```bash
docker compose up -d
```

## Run Migrations

From the `backend` directory:

```bash
alembic upgrade head
```

Check the current migration:

```bash
alembic current
```

## Run Tests

```bash
pytest
```
