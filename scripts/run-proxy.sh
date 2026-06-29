#!/bin/bash
# Start LLM Apipool proxy server - kills any existing process on port first

set -e

PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}

# Kill any existing process on the port
if command -v lsof &> /dev/null; then
    PID=$(lsof -t -i:"$PORT" 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Killing process $PID on port $PORT"
        kill -9 "$PID" 2>/dev/null || true
    fi
elif command -v fuser &> /dev/null; then
    fuser -k "$PORT/tcp" 2>/dev/null || true
fi

# Ensure frontend is built
FRONTEND_DIST="$(dirname "$0")/../web/dist"
if [ ! -d "$FRONTEND_DIST" ]; then
    echo "Frontend not built. Building..."
    cd "$(dirname "$0")/../frontend"
    npm run build
fi

echo "Starting LLM Apipool server on http://${HOST}:${PORT}"
echo "Dashboard: http://localhost:${PORT}/"
echo "API: http://localhost:${PORT}/v1/chat/completions"

exec llm-apipool proxy --port "$PORT" --host "$HOST"