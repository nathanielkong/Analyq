# Analyq

Analyq is an educational full-stack AI stock intelligence platform built with real financial data, backend analysis tools, machine learning, and an AI assistant.

The goal is not to build a stock-picking tool or a thin ChatGPT wrapper. The goal is to build a production-style application where the backend retrieves data, performs calculations, runs model inference where appropriate, and gives the AI assistant structured evidence to explain.

## Docker and Hosting

See [DEPLOYMENT.md](DEPLOYMENT.md) for the container setup, secret configuration,
isolated tests, GitHub image builds and optional Linux VM deployment with HTTPS.
The deployment Compose file is separate from the existing development database;
it does not migrate or delete your current local data. Hosting is not enabled yet.

## Current Phase

Phase 1: Project Architecture and Setup

We are currently establishing the foundation:

- MVP requirements
- Initial architecture
- Repository structure
- Development environment plan
- Basic documentation
- Initial FastAPI backend health check
- React stock research workspace with persistent chat sessions
- Real stock quote lookup through swappable backend market data clients
- PostgreSQL chat history and Alembic migrations
- Gemini-based interpretation and grounded explanation of stock research results

The assistant currently interprets a request, uses recent chat context for follow-up
questions, dispatches trusted backend tools, and explains their results in a
question-specific tabbed response. Stock comparisons, RAG, document citations, and
production ML monitoring remain future work.

## MVP Goal

The minimum viable product should allow a user to:

- Search for a stock symbol
- View basic stock quote information
- View historical price data
- Compare two stocks using backend-calculated metrics
- Understand recent volatility and risk signals
- Ask an AI assistant a stock comparison question and receive a response grounded in backend tool results

Example MVP question:

> Compare NVDA and AMD. Which has been more volatile recently, and what are the major risks of each company?

## Recommended Architecture

We will start with a modular monolith:

```text
User
  |
React + TypeScript frontend
  |
REST API
  |
FastAPI backend
  |
  +-- API routers
  +-- Services
  +-- External API clients
  +-- Database layer
  +-- ML inference module
  +-- AI orchestration module
```

Early backend flow:

```text
API Router -> Service -> Client/Repository -> External API or Database
```

This keeps the project simple enough to learn from while still using a clean separation of responsibilities.

## Planned Repository Structure

```text
.
|-- README.md
|-- .env.example
|-- .gitignore
|-- docs/
|   |-- architecture.md
|   `-- decisions/
|       `-- 0001-initial-architecture.md
|-- frontend/
|   `-- React + TypeScript app
|-- backend/
|   `-- FastAPI app
`-- docker-compose.yml
```

The `frontend`, `backend`, and Docker files will be added incrementally during Phase 1.

## Learning Goals

This project is designed to build practical skill in:

- Full-stack application architecture
- React and TypeScript
- FastAPI and Pydantic
- REST API design
- PostgreSQL and migrations
- External API integration
- Testing with pytest
- Machine learning pipelines
- AI tool calling
- RAG fundamentals
- Docker and CI/CD
- Production documentation

## Non-Goals

For the MVP, we are not trying to:

- Reliably predict future stock prices
- Provide financial advice
- Build a production trading system
- Add every possible AI, ML, and DevOps feature at once
- Implement microservices before the modular monolith has outgrown itself

## Development Principles

- Build small vertical slices.
- Keep financial data access behind backend clients.
- Keep market data providers swappable through configuration.
- Keep business logic in services, not API routes.
- Add ML only when the problem framing is defensible.
- Make AI answers depend on retrieved data and backend tools.
- Prefer readable code over clever abstractions.
- Document important architecture decisions as we make them.

## Suggested First Commit

```text
docs: add initial project architecture
```
