#!/usr/bin/env bash
# setup.sh — first-time local environment setup
#
# Run once after cloning:
#   ./scripts/setup.sh

set -euo pipefail

echo "▶ Setting up backend Python environment..."
cd apps/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "  Created apps/backend/.env from .env.example — fill in your secrets."
fi

cd ../..

echo "▶ Setting up frontend Node environment..."
cd apps/frontend
npm ci

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

cd ../..

echo ""
echo "✓ Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit apps/backend/.env — set GOOGLE_CLOUD_PROJECT and other secrets"
echo "  2. Run: ./scripts/dev.sh"
echo "  3. Open: http://localhost:8000/docs"
