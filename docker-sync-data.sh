#!/bin/bash
# CPM Docker Data Sync — dev 데이터를 Docker 볼륨으로 복사
set -e

CONTAINER_NAME="cpm"
LOCAL_DB="$HOME/.local/share/cpm/cpm.db"
LOCAL_SCREENSHOTS="$(dirname "$0")/static/screenshots"

echo "=== CPM Docker Data Sync ==="

# Check local DB
if [ ! -f "$LOCAL_DB" ]; then
    echo "ERROR: Local DB not found: $LOCAL_DB"
    exit 1
fi

# Check container
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container '$CONTAINER_NAME' is not running."
    echo "Starting with: docker compose up -d"
    docker compose up -d
    sleep 3
fi

# 1. Copy DB
echo ""
echo "[1/2] Copying database..."
echo "  From: $LOCAL_DB"
echo "  To:   $CONTAINER_NAME:/data/cpm.db"
docker cp "$LOCAL_DB" "$CONTAINER_NAME:/data/cpm.db"

# Also copy WAL/journal if exists
[ -f "${LOCAL_DB}-wal" ] && docker cp "${LOCAL_DB}-wal" "$CONTAINER_NAME:/data/cpm.db-wal" 2>/dev/null || true
[ -f "${LOCAL_DB}-journal" ] && docker cp "${LOCAL_DB}-journal" "$CONTAINER_NAME:/data/cpm.db-journal" 2>/dev/null || true
echo "  Done!"

# 2. Copy screenshots
if [ -d "$LOCAL_SCREENSHOTS" ] && [ "$(ls -A "$LOCAL_SCREENSHOTS" 2>/dev/null)" ]; then
    echo ""
    echo "[2/2] Copying screenshots..."
    SCREENSHOT_COUNT=$(ls -1 "$LOCAL_SCREENSHOTS" | wc -l)
    echo "  From: $LOCAL_SCREENSHOTS ($SCREENSHOT_COUNT files)"
    echo "  To:   $CONTAINER_NAME:/app/static/screenshots/"

    for f in "$LOCAL_SCREENSHOTS"/*; do
        [ -f "$f" ] && docker cp "$f" "$CONTAINER_NAME:/app/static/screenshots/"
    done
    echo "  Done!"
else
    echo ""
    echo "[2/2] No screenshots to copy."
fi

# 3. Fix permissions & restart
echo ""
echo "Restarting container..."
docker exec -u root "$CONTAINER_NAME" chown -R cpm:cpm /data /app/static/screenshots 2>/dev/null || true
docker restart "$CONTAINER_NAME"

echo ""
echo "=== Sync complete! ==="
echo "Access: http://localhost:9200"
