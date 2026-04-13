FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CPM_DATA_DIR=/data \
    CPM_DEBUG=false

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY setup.py ./
RUN pip install --no-cache-dir -e . gunicorn whitenoise requests

# Copy application code
COPY . .

# Save screenshots as seed (volume mount will shadow static/screenshots/)
RUN mkdir -p /app/_screenshots_seed && \
    cp -r /app/static/screenshots/* /app/_screenshots_seed/ 2>/dev/null || true

# Collect static files
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Create non-root user and data directory
RUN useradd -r -s /bin/false cpm && \
    mkdir -p /data /app/static/screenshots && \
    chown -R cpm:cpm /data /app

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER cpm

EXPOSE 9200

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9200/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
