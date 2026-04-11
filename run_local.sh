#!/usr/bin/env bash
# Local development server with hot reload.
# Usage: ./run_local.sh
# Then open http://localhost:8000

set -e

cd "$(dirname "$0")"

# Verify .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and set GROQ_API_KEY."
    exit 1
fi

# Use a local chroma dir so it persists between runs
export CHROMA_PATH=./chroma_db_local

# Start FastAPI with hot reload — changes to .py files auto-restart the server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
