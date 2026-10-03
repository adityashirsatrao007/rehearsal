#!/usr/bin/env bash
# Start Rehearsal. Assumes `ollama serve` is already running.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${REHEARSAL_PORT:-8000}"

if [ ! -d .venv ]; then
  echo "→ creating virtualenv"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if ! curl -s --max-time 2 "${OLLAMA_HOST:-http://127.0.0.1:11434}/api/version" >/dev/null; then
  echo "⚠  Ollama is not running. Start it with:  ollama serve"
  echo "   Then pull the model:                  ollama pull gemma2:2b"
fi

echo "→ Rehearsal on http://127.0.0.1:${PORT}"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
