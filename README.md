# temporal-agent-poker

Play No-Limit Texas Hold'em against a GPT-powered AI agent, orchestrated by Temporal workflows with a self-organizing memory system.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    BROWSER                                           │
│                              React + Vite (localhost:5173)                           │
│                                                                                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│   │ Poker Table  │  │ Action Panel │  │  Event Log   │  │  GPT Action Display   │  │
│   └──────────────┘  └──────────────┘  └──────────────┘  └───────────────────────┘  │
└───────────────────────────────────┬─────────────────────────────────────────────────┘
                                    │ WebSocket (actions ↑ state ↓)
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────────────┐
│                          FastAPI SERVER (localhost:8000)                              │
│                   Bridges browser ←→ Temporal (signals + queries)                    │
└───────────────────────────────────┬─────────────────────────────────────────────────┘
                                    │ Temporal Client SDK
                                    │
┌═══════════════════════════════════▼═════════════════════════════════════════════════╗
║                                                                                     ║
║                    TEMPORAL  (localhost:7233 / UI at :8233)                         ║
║                                                                                     ║
║  ┌────────────────────────────────────────────────────────────────────────────┐     ║
║  │                   WORKFLOW: PokerGameWorkflow                               │     ║
║  │                                                                            │     ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐  │     ║
║  │  │  POKERKIT STATE (game rules, cards, pots, evaluation)               │  │     ║
║  │  └─────────────────────────────────────────────────────────────────────┘  │     ║
║  │                                                                            │     ║
║  │  Game Loop:                                                                │     ║
║  │    ┌─────────┐     ┌──────────────────────┐     ┌──────────────────────┐ │     ║
║  │    │ Actor?  │────▶│ Human? wait_condition │────▶│ GPT? execute_activity│ │     ║
║  │    └─────────┘     │ (signal + 30s timer)  │     │ (gpt_decide)        │ │     ║
║  │         ▲          └──────────┬───────────┘     └──────────┬───────────┘ │     ║
║  │         │                     │                             │             │     ║
║  │         └─────────────────────┴─────── apply action ────────┘             │     ║
║  │                                                                            │     ║
║  │  After hand:                                                               │     ║
║  │    reflect (activity) → update running notes → continue_as_new             │     ║
║  │                                                                            │     ║
║  │  Game over:                                                                │     ║
║  │    compress learnings (activity) → write to memory filesystem              │     ║
║  │                                                                            │     ║
║  └────────────────────────────────────────────────────────────────────────────┘     ║
║                                                                                     ║
║  ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║  │  TEMPORAL PROVIDES:                                                          │    ║
║  │                                                                             │    ║
║  │  • Signals ──────── player actions (fold/call/raise) into workflow          │    ║
║  │  • Queries ──────── read game state without blocking (observations)         │    ║
║  │  • Timers ───────── 30s turn timeout → auto-fold (durable, survives crash) │    ║
║  │  • Activities ───── GPT API calls with retry + timeout                      │    ║
║  │  • Replay ───────── crash mid-hand? restart worker, game continues          │    ║
║  │  • Continue-as-new─ multi-hand sessions, bounded memory                     │    ║
║  │  • Event History ── full audit trail of every action + GPT decision         │    ║
║  │                                                                             │    ║
║  └─────────────────────────────────────────────────────────────────────────────┘    ║
║                                                                                     ║
╚═════════════════════════════════════════════════════════════════════════════════════╝
                                    │
                          Activities│(GPT API calls)
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────────────┐
│                              OPENAI API                                              │
│                                                                                     │
│   ┌─────────────────┐  ┌────────────────────┐  ┌─────────────────────────────────┐ │
│   │  gpt_decide     │  │ gpt_reflect_hand   │  │  gpt_compress_learnings         │ │
│   │                 │  │                    │  │                                 │ │
│   │ Pick action     │  │ Update running     │  │ Distill session notes into      │ │
│   │ (fold/call/     │  │ notes after each   │  │ compact persistent learnings    │ │
│   │  raise)         │  │ hand (in-memory)   │  │ (writes to filesystem)          │ │
│   └─────────────────┘  └────────────────────┘  └──────────────────┬──────────────┘ │
└─────────────────────────────────────────────────────────────────────┼────────────────┘
                                                                      │
                                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         AGENT MEMORY FILESYSTEM                                      │
│                         memory/agents/gpt-default/                                   │
│                                                                                     │
│   ┌─────────────────┐  ┌──────────────────────────┐  ┌───────────────────────────┐ │
│   │  strategy.md    │  │  opponents/               │  │  learnings.md             │ │
│   │                 │  │    session_notes.md        │  │                           │ │
│   │  Self-defined   │  │                            │  │  General insights from    │ │
│   │  poker strategy │  │  Compressed opponent       │  │  past sessions            │ │
│   │  (evolves over  │  │  profiles from past games  │  │                           │ │
│   │  sessions)      │  │                            │  │                           │ │
│   └─────────────────┘  └──────────────────────────┘  └───────────────────────────┘ │
│                                                                                     │
│   Agent defines its own structure. Files persist across games.                       │
│   Loaded into GPT's system prompt at the start of each session.                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW (one turn)                                         │
│                                                                                     │
│  1. Player clicks "Raise $20"                                                       │
│  2. Browser → WebSocket → FastAPI → signal(player_action, {raise, 20})              │
│  3. Workflow: wait_condition unblocks → PokerKit applies action → street advances   │
│  4. Workflow: actor is now GPT → execute_activity(gpt_decide)                       │
│  5. GPT activity: loads memory + running notes → calls OpenAI → returns action      │
│  6. Workflow: applies GPT action → PokerKit deals next card if street complete      │
│  7. FastAPI: polls query(get_observation) → pushes state_update over WebSocket      │
│  8. Browser: re-renders table with new cards, pot, GPT's action badge              │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         MEMORY LIFECYCLE                                              │
│                                                                                     │
│  Hand 1: GPT plays → (no notes yet)                                                │
│  Hand 1 ends: gpt_reflect_hand → "Opponent raised big with weak hand"              │
│                                                                                     │
│  Hand 2: GPT plays → (sees running notes: "opponent is aggressive")                │
│  Hand 2 ends: gpt_reflect_hand → appends "Opponent bluffs river frequently"        │
│                                                                                     │
│  Hand 3-N: Notes accumulate in-memory, passed via continue_as_new                  │
│                                                                                     │
│  Game Over (someone busted):                                                        │
│    gpt_compress_learnings → distills notes → writes strategy.md, learnings.md      │
│                                                                                     │
│  Next Game: GPT loads persistent files → starts with prior knowledge               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- **PokerKit** — game rules, dealing, pot math, hand evaluation
- **Temporal** — durable orchestration, turn timers, crash recovery, event history
- **OpenAI GPT** — AI opponent (runs as a Temporal Activity)
- **React + Vite** — poker table UI with real-time WebSocket updates

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Temporal CLI](https://docs.temporal.io/cli#install)
- tmux
- OpenAI API key

On Debian/Ubuntu/WSL, install the Python venv package if it is not already present:

```bash
sudo apt install python3.12-venv
```

## Setup

```bash
cd poker_temporal

# Frontend
cd frontend
npm install
cd ..
```

`start.sh` creates or repairs `poker_temporal/.venv` automatically, upgrades pip, and installs `requirements.txt` when dependencies are missing. It also prompts for your OpenAI API key on first run and saves it to `poker_temporal/.env`.

You can also create `.env` yourself:

```
OPENAI_API_KEY=sk-your-key-here
```

## Running

From the repo root:

```bash
./start.sh
```

The script starts all services in a tmux session named `poker`:

- Temporal dev server
- Temporal worker
- FastAPI server
- Vite frontend

Open **http://localhost:5173** and click "New Game".

Useful tmux commands:

```bash
tmux attach -t poker
tmux kill-session -t poker
```

If you prefer to run services manually, use 4 terminals:

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

## How Temporal Made This Possible

### What Temporal does in this project

**1. Game state that survives anything**
The PokerKit state lives inside a workflow. If the worker crashes mid-hand, Temporal replays the workflow from its event history and reconstructs the exact same game state. We wrote zero persistence code — no database, no save/load, nothing.

**2. Turn-based coordination without race conditions**
One workflow = one single-threaded game loop. Player actions arrive as signals and queue up. No locks, no "check if it's your turn" database queries. `wait_condition` blocks until the right player acts.

**3. GPT as a durable activity**
The OpenAI API call runs as a Temporal activity with automatic retries and timeouts. If GPT takes too long or the API errors, Temporal handles retry/fallback. We didn't build any retry logic ourselves.

**4. Turn timers for free**
`wait_condition(timeout=30s)` gives us "auto-fold if player disconnects" in one line. The timer is durable — survives worker restarts.

**5. Multi-hand sessions via continue-as-new**
Each hand is its own workflow execution. Stacks and running notes carry over via `continue_as_new`. Bounded memory, no event history growth problem.

**6. Agent memory rides on the event history**
Every GPT decision (with its memory updates) is recorded as an activity result in Temporal's event history. We get a full audit trail of the agent's learning trajectory without building anything — just query the workflow history.

**7. The entire backend is ~200 lines**
`poker_workflow.py` + `activities.py` + `worker.py`. No web framework for game state, no Redis for pub/sub, no Postgres for persistence, no Celery for async tasks, no cron for timers. Temporal replaced all of that.

### What we would have needed without Temporal

| Concern | Without Temporal | With Temporal |
|---------|-----------------|---------------|
| Game state persistence | PostgreSQL + ORM + migrations | Workflow state (automatic) |
| Real-time updates + turn locking | Redis pub/sub + distributed locks | Signals + queries |
| Async GPT calls with retry | Celery + Redis broker + retry config | Activities (built-in) |
| Turn timeouts | Custom timer service + dead-letter queue | `wait_condition(timeout=30s)` |
| Audit trail | Event sourcing table + custom schema | Event history (free) |
| Crash recovery | Custom replay logic + checkpointing | Deterministic replay (automatic) |
| Multi-hand sessions | State checkpointing + cleanup jobs | `continue_as_new` |
| **Total extra infrastructure** | **5-6 additional services** | **None** |
