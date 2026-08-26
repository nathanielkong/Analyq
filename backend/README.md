# Backend

FastAPI backend for the AI Stock Intelligence Platform.

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

## Run Tests

```bash
pytest
```
