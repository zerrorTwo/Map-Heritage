#!/bin/bash
# Start the Heritage Travel System
# Usage: bash start.sh [--docker] [--gateway] [--ai] [--all]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Vietnam Heritage Travel System v1.0  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

install_deps() {
    echo -e "${YELLOW}[1/4] Installing Python dependencies...${NC}"
    if [ ! -d ".venv" ]; then
        echo -e "${YELLOW}  → Creating virtual environment...${NC}"
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -r requirements.txt -q
    echo -e "${GREEN}  ✓ Dependencies installed${NC}"
}

start_infra() {
    echo -e "${YELLOW}[2/4] Starting infrastructure (PostGIS + Redis + OSRM)...${NC}"
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d postgis redis osrm
    elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
        docker compose up -d postgis redis osrm
    else
        echo -e "${RED}  ✗ Docker not found. Skipping infrastructure.${NC}"
        echo -e "${YELLOW}  → AI service will use in-memory seed data.${NC}"
    fi
    echo -e "${GREEN}  ✓ Infrastructure started${NC}"
}

start_ai() {
    echo -e "${YELLOW}[3/4] Starting AI Service on port 8001...${NC}"
    source .venv/bin/activate
    PYTHONPATH="$PROJECT_DIR" python -m services.ai_service.main &
    AI_PID=$!
    echo -e "${GREEN}  ✓ AI Service started (PID: $AI_PID)${NC}"
    echo "  → http://localhost:8001/docs"
}

start_gateway() {
    echo -e "${YELLOW}[4/4] Starting API Gateway on port 8000...${NC}"
    source .venv/bin/activate
    PYTHONPATH="$PROJECT_DIR" python -m api_gateway.main &
    GW_PID=$!
    echo -e "${GREEN}  ✓ API Gateway started (PID: $GW_PID)${NC}"
    echo "  → http://localhost:8000"
    echo "  → http://localhost:8000/docs"
}

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $AI_PID $GW_PID 2>/dev/null || true
    echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT

install_deps
start_infra
start_ai
sleep 2
start_gateway

echo ""
echo "Press Ctrl+C to stop all services."
wait
