#!/bin/bash
set -e

SESSION="poker"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)/poker_temporal"

# Check prerequisites
command -v temporal >/dev/null 2>&1 || { echo "Error: temporal CLI not found. Install from https://docs.temporal.io/cli#install"; exit 1; }
command -v tmux >/dev/null 2>&1 || { echo "Error: tmux not found. Install with: brew install tmux"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Error: node not found. Install Node.js 18+"; exit 1; }

# Check Python venv exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Error: Python venv not found. Run: cd poker_temporal && uv venv --python 3.11 && uv pip install -r requirements.txt"
    exit 1
fi

# Check frontend node_modules
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "Error: Frontend dependencies not installed. Run: cd poker_temporal/frontend && npm install"
    exit 1
fi

# Check for OpenAI API key
if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env" 2>/dev/null || true
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "No OpenAI API key found."
    read -p "Enter your OpenAI API key: " api_key
    if [ -z "$api_key" ]; then
        echo "Error: API key is required."
        exit 1
    fi
    echo "OPENAI_API_KEY=$api_key" > "$PROJECT_DIR/.env"
    echo "Saved to $PROJECT_DIR/.env"
fi

# Kill existing session if present
tmux kill-session -t $SESSION 2>/dev/null || true

echo "Starting poker game services..."

# Create tmux session with Temporal server
tmux new-session -d -s $SESSION -n temporal -c "$PROJECT_DIR"
tmux send-keys -t $SESSION:temporal "temporal server start-dev" Enter

sleep 2

# Worker pane
tmux new-window -t $SESSION -n worker -c "$PROJECT_DIR"
tmux send-keys -t $SESSION:worker "source .venv/bin/activate && export \$(cat .env | xargs) && python worker.py" Enter

# API server pane
tmux new-window -t $SESSION -n api -c "$PROJECT_DIR"
tmux send-keys -t $SESSION:api "source .venv/bin/activate && export \$(cat .env | xargs) && uvicorn server.app:app --port 8000" Enter

# Frontend pane
tmux new-window -t $SESSION -n frontend -c "$PROJECT_DIR/frontend"
tmux send-keys -t $SESSION:frontend "npm run dev" Enter

# Wait for services to start
sleep 3

echo ""
echo "========================================="
echo "  Poker vs GPT — All services running!"
echo "========================================="
echo ""
echo "  UI:           http://localhost:5173"
echo "  API:          http://localhost:8000"
echo "  Temporal UI:  http://localhost:8233"
echo ""
echo "  tmux session: $SESSION"
echo "  Attach with:  tmux attach -t $SESSION"
echo "  Stop with:    tmux kill-session -t $SESSION"
echo ""
echo "========================================="
echo ""
echo "Open http://localhost:5173 to play!"
