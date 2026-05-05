# temporal-agent-poker

Play No-Limit Texas Hold'em against a GPT-powered AI agent, orchestrated by Temporal workflows with a self-organizing memory system.

## Architecture

```
Browser (React) ←── WebSocket ──→ FastAPI Server ←── Temporal Client ──→ Temporal Workflow
                                                                              │
                                                                         PokerKit State
                                                                              │
                                                                    GPT Agent (Activity)
                                                                              │
                                                                     Memory Filesystem
```

- **PokerKit** — game rules, dealing, pot math, hand evaluation
- **Temporal** — durable orchestration, turn timers, crash recovery, event history
- **OpenAI GPT** — AI opponent (runs as a Temporal Activity)
- **React + Vite** — poker table UI with real-time WebSocket updates

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Temporal CLI](https://docs.temporal.io/cli#install)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- OpenAI API key

## Setup

```bash
cd poker_temporal

# Python environment
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt

# Frontend
cd frontend
npm install
cd ..

# Environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

Create a `.env` file in `poker_temporal/`:
```
OPENAI_API_KEY=sk-your-key-here
```

## Running

You need 4 terminals:

**Terminal 1 — Temporal Server**
```bash
temporal server start-dev
```

**Terminal 2 — Worker** (runs the game workflow + GPT activities)
```bash
cd poker_temporal
source .venv/bin/activate
python worker.py
```

**Terminal 3 — API Server** (WebSocket bridge)
```bash
cd poker_temporal
source .venv/bin/activate
uvicorn server.app:app --reload --port 8000
```

**Terminal 4 — Frontend**
```bash
cd poker_temporal/frontend
npm run dev
```

Open **http://localhost:5173** and click "New Game".

## CLI Mode (no UI)

```bash
cd poker_temporal
source .venv/bin/activate
python main.py
```

## How It Works

### Game Flow
1. Click "New Game" → starts a Temporal workflow
2. PokerKit manages all game rules (blinds, dealing, betting, evaluation)
3. Your actions are sent as Temporal signals
4. GPT's decisions run as Temporal activities
5. Hands continue until one player is busted

### Agent Memory System

The GPT agent has a two-tier memory:

**In-game (running notes):** After each hand, the agent reflects and updates session notes about your play style. These live in memory and are passed between hands — no filesystem noise.

**Post-game (compressed learnings):** When someone goes bust, the agent distills its session notes into compact, reusable learnings saved to disk. These persist across games.

```
memory/agents/gpt-default/
├── strategy.md              # Self-defined poker strategy
├── learnings.md             # General insights from past sessions
└── opponents/
    └── session_notes.md     # Compressed opponent profiles
```

The agent defines and evolves this structure itself.

### Temporal Features Demonstrated

| Feature | Usage |
|---------|-------|
| Signals | Player actions (fold/call/raise) |
| Queries | Game state observations |
| Activities | GPT decisions, reflections |
| Timers | 30s turn timeout → auto-fold |
| Continue-as-new | Multi-hand sessions |
| Durability | Kill the worker mid-hand, restart, game resumes |

### Observability

- **Temporal Web UI:** http://localhost:8233 — view workflow history, signals, activity results
- **Debug query:** `temporal workflow query --workflow-id <id> --type debug_state`
- **Memory log:** `temporal workflow query --workflow-id <id> --type get_memory_log`

## Project Structure

```
poker_temporal/
├── workflow/
│   ├── poker_workflow.py      # Temporal workflow (game engine)
│   ├── activities.py          # GPT decide, reflect, compress
│   └── types.py               # Observation, Action, SessionState
├── env/
│   └── poker_env.py           # Gym-style async wrapper
├── server/
│   └── app.py                 # FastAPI + WebSocket bridge
├── frontend/
│   └── src/
│       ├── App.tsx            # Main app
│       ├── components/        # PokerTable, Card, ActionPanel, etc.
│       ├── hooks/             # useGameSocket WebSocket hook
│       └── styles/            # Poker table CSS
├── memory/agents/             # GPT self-organizing memory
├── worker.py                  # Temporal worker
├── main.py                    # CLI mode
└── requirements.txt
```

## Demo Script

1. Open the browser, start a game
2. Play a few hands — show cards, actions, GPT responding
3. Point at the Event Log: "Every action is a Temporal signal"
4. **Kill the worker process** mid-hand → game pauses
5. Restart worker → game resumes exactly where it left off
6. Open Temporal Web UI → show full event history
7. After the game ends, `ls memory/agents/gpt-default/` — show what GPT learned
8. "200 lines of game logic, zero persistence code"
