FROM python:3.11-slim

# curl is used as a fallback HTTP client in http_util.py (handles
# TLS renegotiation cases that Python's urllib chokes on).
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sy_valuation/ ./sy_valuation/

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080

# /api/health 가 ok 인지로 헬스체크
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-8080}/api/health || exit 1

CMD ["python", "-m", "sy_valuation.run"]
