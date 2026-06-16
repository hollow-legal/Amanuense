# ── API ────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS api
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[api]"
COPY pipeline/ pipeline/
COPY api/ api/
COPY db/ db/
COPY alembic.ini entrypoint.sh ./
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]

# ── MCP (validação de citações legais via streamable-http) ────────────────────
FROM api AS mcp
# o install editable roda antes do COPY do código; o PYTHONPATH garante o import
ENV PYTHONPATH=/app
EXPOSE 8765
CMD ["amanuense", "mcp", "--http", "--port", "8765"]

# ── Web ────────────────────────────────────────────────────────────────────────
FROM nginx:alpine AS web
COPY frontend/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf
