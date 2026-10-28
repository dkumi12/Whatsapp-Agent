#!/usr/bin/env bash
# =============================================================
# deploy.sh — Zero-downtime deploy to whatsapp-bridge-vm
# Run via GitHub Actions or manually:
#   gcloud compute ssh abami@whatsapp-bridge-vm \
#     --zone=us-central1-a --project=whatsapp-agent-507202 \
#     --command="bash /home/abami/Whatsapp-Agent/scripts/deploy.sh"
# =============================================================
set -euo pipefail

APP_DIR="/home/abami/Whatsapp-Agent"
VENV="$APP_DIR/venv/bin"

echo "🚀 Starting deploy at $(date)"
cd "$APP_DIR"

# ── 1. Pull latest code ─────────────────────────────────────
echo "📦 Pulling latest from main..."
git fetch origin main

# Remove any untracked files that would block the pull (Error #6)
git checkout origin/main -- bridge/index.js src/api.py src/config.py src/cohorts.py 2>/dev/null || true
git pull origin main
echo "✅ Code updated"

# ── 2. Sync Python dependencies (Error #4) ──────────────────
echo "📦 Syncing Python dependencies..."
"$VENV/pip" install -r requirements.txt --quiet
echo "✅ Dependencies synced"

# ── 3. Verify PREFECT_JID is set (Error #2) ─────────────────
if ! grep -q "PREFECT_JID" "$APP_DIR/.env"; then
    echo "⚠️  PREFECT_JID missing from .env — adding now..."
    echo 'PREFECT_JID=233205265381@s.whatsapp.net' >> "$APP_DIR/.env"
fi
echo "✅ PREFECT_JID confirmed in .env"

# ── 4. Restart services with updated env (Error #11) ────────
echo "♻️  Restarting PM2 processes with --update-env..."
pm2 restart whatsapp-bridge --update-env
pm2 restart fastapi-backend --update-env
echo "✅ PM2 processes restarted"

# ── 5. Wait and health-check backend ────────────────────────
echo "🏥 Waiting for backend health..."
for i in {1..12}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo "✅ Backend is healthy (attempt $i)"
        break
    fi
    echo "   Attempt $i/12: status=$STATUS, retrying in 5s..."
    sleep 5
    if [ "$i" -eq 12 ]; then
        echo "❌ Backend did not become healthy after 60s"
        pm2 logs fastapi-backend --lines 20 --nostream
        exit 1
    fi
done

# ── 6. Check queue backlog (Error #8) ───────────────────────
QUEUE_FILE="$APP_DIR/bridge/queue.jsonl"
if [ -f "$QUEUE_FILE" ]; then
    QUEUE_COUNT=$(wc -l < "$QUEUE_FILE" || echo 0)
    if [ "$QUEUE_COUNT" -gt 0 ]; then
        echo "⚠️  Warning: queue.jsonl has $QUEUE_COUNT buffered message(s) — will replay automatically"
    else
        echo "✅ queue.jsonl is empty"
    fi
fi

echo ""
echo "🎉 Deploy complete at $(date)"
pm2 list
