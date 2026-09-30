FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend/src

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
COPY backend/README.md backend/README.md

# Most dependencies install from wheels on amd64. Build tools are present only
# during installation in case a scientific/solver dependency needs a fallback
# compile path, then removed from the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && python -m pip install --upgrade pip \
    && python -m pip install ./backend \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1

CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
