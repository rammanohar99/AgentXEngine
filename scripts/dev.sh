#!/usr/bin/env bash
# dev.sh — start the full local development environment
#
# Usage:
#   ./scripts/dev.sh          # start postgres + redis + backend (hot-reload)
#   ./scripts/dev.sh --full   # also start frontend dev server
#
# Prerequisites:
#   - Docker + Docker Compose
#   - Python 3.12+ with venv at apps/backend/.venv
#   - Node 22+ with npm

set -euo pipefail

FULL=false
if [[ "${1:-}" == "--full" ]]; then
  FULL=true
fi

echo "▶ Starting infrastructure (postgres, redis)..."
docker compose up -d postgres redis

echo "▶ Waiting for postgres to be healthy..."
until docker compose exec postgres pg_isready -U postgres -d aiengos &>/dev/null; do
  sleep 1
done

echo "▶ Waiting for redis to be healthy..."
until docker compose exec redis redis-cli ping &>/dev/null; do
  sleep 1
done

echo "▶ Running database migrations..."
(cd apps/backend && alembic upgrade head)

echo "▶ Starting backend (hot-reload on :8000)..."
(cd apps/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

if $FULL; then
  echo "▶ Starting frontend dev server (on :5173)..."
  (cd apps/frontend && npm run dev) &
  FRONTEND_PID=$!
fi

echo ""
echo "✓ Dev environment running"
echo "  Backend:  http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
if $FULL; then
  echo "  Frontend: http://localhost:5173"
fi
echo ""
echo "Press Ctrl+C to stop all services."

# Wait and clean up on exit
trap 'kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null; docker compose stop postgres redis' EXIT
wait
