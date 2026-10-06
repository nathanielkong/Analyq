FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app
RUN groupadd --gid 10001 analyq && useradd --uid 10001 --gid analyq --no-create-home analyq
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY alembic ./alembic
USER analyq
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

FROM runtime AS test
USER root
COPY requirements-dev.lock ./
RUN pip install --require-hashes -r requirements-dev.lock
COPY tests ./tests
USER analyq
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

# A plain `docker build backend` must produce the app, not the test runner.
FROM runtime AS production
