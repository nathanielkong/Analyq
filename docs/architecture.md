# Architecture

This document describes the intended architecture for the AI Stock Intelligence Platform. It will evolve as the project grows.

## System Overview

```text
                    User
                     |
            React + TypeScript
                     |
                  REST API
                     |
                  FastAPI
                     |
      +--------------+---------------+
      |              |               |
 PostgreSQL     Market Data     AI Orchestrator
                     |               |
              External APIs          |
                                     |
                        +------------+------------+
                        |            |            |
                  Backend Tools     RAG      ML Inference
                        |            |            |
                        +------------+------------+
                                     |
                              AI Explanation
```

## Initial Architecture Style

We will use a modular monolith.

That means the backend starts as one FastAPI application, but the code is organized into clear modules. This is simpler than microservices and better for learning, local development, testing, and deployment at this stage.

We can separate services later if the project grows enough to justify it.

## Backend Layers

The backend should usually follow this flow:

```text
API Router -> Service -> Client/Repository -> External API or Database
```

### API Routers

Routers handle HTTP-specific concerns:

- Request paths
- Query parameters
- Request and response schemas
- HTTP status codes
- Calling the correct service

Routers should not contain complex business logic.

### Services

Services contain business logic:

- Comparing stocks
- Calculating volatility
- Building portfolio summaries
- Coordinating multiple data sources
- Preparing structured results for the AI assistant

The stock comparison logic should live in a service layer so it can be reused by both API endpoints and future AI tools.

### Clients

Clients communicate with external systems:

- Market data providers
- News providers
- LLM providers
- Embedding providers

External API calls should be isolated here instead of scattered throughout the codebase.

### Repositories

Repositories will handle database access once PostgreSQL is introduced.

Examples:

- Users
- Watchlists
- Portfolio holdings
- Chat sessions
- ML predictions

## Frontend Architecture

The frontend will be a React and TypeScript application.

Initial responsibilities:

- Display stock search and result views
- Call backend REST endpoints
- Show loading, empty, and error states
- Present stock comparison results clearly

The frontend should not perform authoritative financial calculations that belong in the backend.

## Database Architecture

PostgreSQL will be introduced after the basic frontend and backend are connected.

Likely early tables:

- users
- watchlists
- watchlist_items
- portfolio_holdings
- chat_sessions
- chat_messages

Authentication may be deferred until after the first full-stack stock-data slice is working.

## ML Architecture

The first ML feature should be small and defensible.

Recommended initial task:

- volatility or risk-level classification

Avoid claiming reliable future price prediction. The ML system should demonstrate sound engineering practices:

```text
Data -> Features -> Time-series split -> Training -> Evaluation -> Artifact -> Inference API
```

## AI Assistant Architecture

The future AI assistant should use backend tools rather than inventing answers.

Target flow:

```text
User Question
  -> Intent / tool selection
  -> Backend tools
  -> Structured financial data
  -> LLM explanation
  -> User-facing answer with evidence
```

Early tools may include:

- get_stock_price
- get_price_history
- calculate_volatility
- compare_stocks
- get_company_news
- get_ml_prediction

## RAG Architecture

RAG is a later phase.

Target flow:

```text
Documents -> Parsing -> Chunking -> Embeddings -> Vector Search -> Context -> LLM
```

We should only add RAG after the basic data-backed assistant works.

## Deployment Direction

Initial local development:

- Frontend dev server
- FastAPI dev server
- PostgreSQL through Docker Compose later

Potential production deployment:

- Frontend on Vercel
- Backend on a cloud service such as Render, Fly.io, AWS, or similar
- PostgreSQL through Supabase or another managed provider

The exact deployment choice can wait until the app has a useful vertical slice.
