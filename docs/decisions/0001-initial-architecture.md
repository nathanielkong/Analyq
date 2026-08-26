# 0001: Initial Architecture

Date: 2026-08-26

Status: Accepted

## Context

The AI Stock Intelligence Platform is a learning-focused portfolio project. It needs to demonstrate full-stack engineering, financial data integration, machine learning, AI tool calling, and eventually production deployment.

The project should remain understandable enough for a graduate engineering interview. It should avoid unnecessary complexity while still using architecture patterns that resemble production software.

## Decision

We will start with a monorepo containing:

- a React and TypeScript frontend
- a Python FastAPI backend
- documentation for architecture and decisions
- later Docker Compose support for local infrastructure

The backend will start as a modular monolith using this general flow:

```text
API Router -> Service -> Client/Repository -> External API or Database
```

Business logic, such as stock comparison and volatility calculation, will live in service modules rather than directly inside API route handlers.

External market data calls will be isolated behind client classes or functions.

Database access will later be isolated behind repositories or clearly scoped data-access modules.

## Rationale

This approach gives us:

- a simple development and deployment model
- a clear separation of responsibilities
- reusable backend logic for both API endpoints and future AI tools
- an architecture that can grow without starting with microservices
- a codebase that is easier to explain in interviews

Starting with microservices would add infrastructure complexity before the product needs it.

## Consequences

Positive consequences:

- Faster development during Phase 1
- Easier local testing
- Clear learning path for frontend, backend, APIs, and services
- AI tools can reuse backend services later

Tradeoffs:

- The backend may eventually need clearer module boundaries as features grow
- Long-running ML training should not run inside normal request handlers
- Some future components may need to move into background jobs or separate services

## Deferred Decisions

We are intentionally not deciding yet:

- which financial data provider to use
- which authentication provider to use
- where to deploy production services
- which ML model family to use
- which vector database to use for RAG
- whether any module should become a separate service

These decisions should be made when the project has enough implementation context.
