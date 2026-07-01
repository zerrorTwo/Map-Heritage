#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE=(docker compose)

if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    COMPOSE=()
  fi
fi

print_urls() {
  printf '\nVietnam Heritage Travel is starting.\n'
  printf 'Frontend:    http://localhost:3000\n'
  printf 'API is proxied through the frontend at /api.\n\n'
}

start_docker() {
  if [ ${#COMPOSE[@]} -eq 0 ]; then
    printf 'Docker Compose was not found. Install Docker or run: bash start.sh --local\n' >&2
    exit 1
  fi

  cd "$PROJECT_DIR"
  print_urls
  "${COMPOSE[@]}" up --build
}

start_local() {
  cd "$PROJECT_DIR"

  if [ ${#COMPOSE[@]} -gt 0 ]; then
    "${COMPOSE[@]}" up -d osrm
  else
    printf 'Warning: Docker Compose not found, OSRM will not be started for local mode.\n' >&2
  fi

  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt

  PYTHONPATH="$PROJECT_DIR" OSRM_BASE_URL="${OSRM_BASE_URL:-http://localhost:5000}" uvicorn services.ai_service.main:app --host 0.0.0.0 --port 8001 &
  AI_PID=$!
  PYTHONPATH="$PROJECT_DIR" AI_SERVICE_URL="${AI_SERVICE_URL:-http://localhost:8001}" uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000 &
  API_PID=$!

  cd "$PROJECT_DIR/frontend"
  if [ ! -d node_modules ]; then
    npm install
  fi
  npm run dev &
  FE_PID=$!

  cleanup() {
    kill "$AI_PID" "$API_PID" "$FE_PID" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM

  printf '\nLocal mode is running.\n'
  printf 'Frontend:    http://localhost:5173\n'
  printf 'API Gateway: http://localhost:8000/docs\n'
  printf 'AI Service:  http://localhost:8001/docs\n\n'
  wait
}

case "${1:-}" in
  --local)
    start_local
    ;;
  --help|-h)
    printf 'Usage: bash start.sh [--local]\n'
    printf 'Default: run full stack with Docker Compose.\n'
    ;;
  *)
    start_docker
    ;;
esac
