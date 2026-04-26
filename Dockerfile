FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PT_LOG_FORMAT=json

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first so they cache when only source changes
COPY pyproject.toml README.md ./
COPY pt ./pt
RUN pip install --upgrade pip && pip install -e .

# Drop privileges
RUN useradd --create-home --uid 10001 ptuser \
 && chown -R ptuser:ptuser /app
USER ptuser

EXPOSE 8430

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8430/api/health').read()" || exit 1

CMD ["uvicorn", "pt.api.app:app", "--host", "0.0.0.0", "--port", "8430"]
