# Agent Architecture

The Claude poker agent has a **file-system-based memory** that it owns and
structures itself. The objective is to get better at poker by playing and
observing games over time.

This document is a module-level companion to
[poker_game_architecture.md](poker_game_architecture.md). The main architecture
keeps the system overview; this file owns all agent decision-making, model-call,
resilience, tool-loop, and memory details.

---

## Design Principles

1. **Agent-defined structure** — The agent decides how to organize its memory, not the application.
2. **Bootstrap from empty** — If the memory folder is empty, the agent defines its schema on first run.
3. **Learning objective** — Memory exists to improve poker decisions over time.
4. **Persistent across sessions** — Memory survives between hands, games, and process restarts.
5. **Tool-driven access** — Memory is not loaded wholesale into model context. The model makes tool calls to inspect and update the filesystem.

---

## Code Placement

All workflow code in this document belongs under `workflows/`. All activity code
belongs under `activities/`.

| Code | Target location | Purpose |
|------|-----------------|---------|
| Agent tool loop workflow helpers | `workflows/agent.py` | Route Claude tool calls to memory activities |
| Post-hand reflection workflow helper | `workflows/agent.py` | Let Claude inspect and update memory after a hand |
| Claude model-call activity | `activities/agent.py` | Call the model once and return either an action or a tool call |
| Memory filesystem activities | `activities/agent_memory.py` | List, read, write, and targeted-edit memory files |

---

## Agent Decision Model

The production design runs Claude as a Temporal activity invoked by the game
workflow. The workflow owns turn order and timeouts; the agent activity owns
model interaction, action parsing, tool calls, retries, and fallback behavior.

For early CLI-only prototypes, the same prompt/parsing logic can be wrapped in a
plain `ClaudePokerAgent` class. That class is agent code and should live with
the agent module, not in the poker workflow or UI architecture.

---

## CLI Prototype Agent

Target file: `activities/agent.py` or a prototype-only module under `agents/`

```python
import anthropic


class ClaudePokerAgent:
    """Claude Opus 4.7 as a poker player."""

    def __init__(self, player_index: int):
        self.client = anthropic.Anthropic()
        self.model = "claude-opus-4-7-20250506"
        self.player_index = player_index

    async def act(self, obs: Observation, valid_actions: list[Action]) -> Action:
        prompt = self._build_prompt(obs, valid_actions)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            system=(
                "You are an expert poker player. Analyze the situation and "
                "choose the optimal action. Respond with ONLY one of: "
                "fold | check_or_call | raise <amount>"
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text, valid_actions)

    def _build_prompt(self, obs: Observation, valid_actions: list[Action]) -> str:
        return f"""Current poker situation:

Your hand: {obs.hole_cards}
Community cards: {obs.board_cards or "None"}
Pot: {obs.pot}
Your stack: {obs.stacks[self.player_index]}
Amount to call: {obs.current_bet}
Min raise to: {obs.min_raise}
Max raise to: {obs.max_raise}
Street: {obs.street}

Action history:
{self._format_history(obs.history)}

Valid actions: {[f"{a.type}" + (f" {a.amount}" if a.amount else "") for a in valid_actions]}

What is your action?"""

    def _format_history(self, history: list[ActionRecord]) -> str:
        if not history:
            return "  (none yet)"
        lines = []
        for rec in history:
            amt = f" to {rec.action.amount}" if rec.action.amount else ""
            lines.append(f"  Player {rec.player_index}: {rec.action.type}{amt} ({rec.street})")
        return "\n".join(lines)

    def _parse_response(self, text: str, valid_actions: list[Action]) -> Action:
        text = text.strip().lower()
        if "fold" in text:
            return Action("fold")
        elif "raise" in text:
            parts = text.split()
            for part in parts:
                try:
                    amount = int(part)
                    return Action("raise", amount)
                except ValueError:
                    continue
            raise_actions = [a for a in valid_actions if a.type == "raise"]
            return raise_actions[0] if raise_actions else Action("check_or_call")
        else:
            return Action("check_or_call")
```

---

## Claude Activity

Moving Claude from an external polling client to a workflow activity simplifies
the runtime architecture:

- The workflow controls Claude's turn directly.
- Timeouts on Claude are handled by activity timeout.
- The human/browser is the only external gameplay client.
- Agent retries and fallback behavior are isolated in activity code.

Target file: `activities/agent.py`

```python
from temporalio import activity
import anthropic


@activity.defn
async def claude_decide(obs_dict: dict, valid_actions_dict: list[dict]) -> dict:
    """Activity: ask Claude for a poker decision."""
    client = anthropic.AsyncAnthropic()

    prompt = _build_prompt(obs_dict, valid_actions_dict)

    response = await client.messages.create(
        model="claude-opus-4-7-20250506",
        max_tokens=256,
        system=(
            "You are an expert poker player. Analyze the situation and "
            "choose the optimal action. Respond with ONLY one of: "
            "fold | check_or_call | raise <amount>"
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip().lower()
    return _parse_to_dict(text, valid_actions_dict)
```

Target file: `workflows/poker_game.py`

```python
if actor == CLAUDE_INDEX:
    obs_dict = self._build_obs_dict(actor)
    valid_dict = self._build_valid_actions_dict(actor)
    try:
        action_dict = await workflow.execute_activity(
            claude_decide,
            args=[obs_dict, valid_dict],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        action = Action(**action_dict)
    except ActivityError:
        action = Action("check_or_call")
    self._apply_action(actor, action)
```

---

## Agent Resilience

The Claude API can timeout, return 500s, or produce unparseable responses. The
agent activity should retry briefly, validate the returned action against the
legal action set, and fall back to a safe action.

```python
class ClaudePokerAgent:
    MAX_RETRIES = 2
    TIMEOUT = 10  # seconds

    async def act(self, obs: Observation, valid_actions: list[Action]) -> Action:
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=256,
                    timeout=self.TIMEOUT,
                    system="...",
                    messages=[{"role": "user", "content": self._build_prompt(obs, valid_actions)}],
                )
                action = self._parse_response(response.content[0].text, valid_actions)
                if action.type == "raise" and action.amount > 0:
                    valid_raise = any(a.type == "raise" for a in valid_actions)
                    if not valid_raise:
                        return Action("check_or_call")
                return action
            except (anthropic.APITimeoutError, anthropic.APIError):
                if attempt < self.MAX_RETRIES:
                    continue
                return Action("check_or_call")
            except Exception:
                return Action("check_or_call")
```

---

## File System Layout

```
memory/
└── agents/
    └── {AGENT_NAME_ID}/           # e.g., "claude-A8CD3/"
        ├── SYSTEM_PROMPT.md       # Agent's self-defined identity + goals
        └── ... (agent-defined)    # Agent creates its own structure below
```

---

## Bootstrap Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Agent starts up                                                 │
│                                                                  │
│  ┌──────────────────┐     YES     ┌──────────────────────────┐ │
│  │ Is memory folder  │───────────►│ Expose memory tools       │ │
│  │ populated?        │            │ Let model inspect files   │ │
│  └──────────────────┘            └──────────────────────────┘ │
│          │ NO                                                    │
│          ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Define memory structure:                                  │   │
│  │  - What categories to track                               │   │
│  │  - What file structure to use                             │   │
│  │  - What to observe and record                             │   │
│  │  - Write SYSTEM_PROMPT.md with objectives                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Example Agent-Defined Structure

On first run, the agent might create something like:

```
memory/agents/claude-A8CD3/
├── SYSTEM_PROMPT.md              # "I am a poker agent. My goal is to..."
├── strategy/
│   ├── preflop_ranges.md         # Opening hand ranges by position
│   ├── bet_sizing.md             # Learned bet sizing patterns
│   └── bluff_frequency.md        # When bluffs worked vs didn't
├── opponent_models/
│   ├── human_player_0.md         # Tendencies: "calls too much, rarely 3-bets"
│   └── patterns.md               # General reads
├── hand_history/
│   ├── notable_hands.md          # Hands worth remembering
│   └── mistakes.md               # Bad outcomes + analysis
└── meta/
    ├── session_stats.md          # Win rate, hands played, profit/loss
    └── learnings.md              # High-level strategic adjustments
```

This is **not prescribed**. The agent creates whatever structure helps it
improve.

---

## Workflow Integration

Target file: `workflows/agent.py`

```python
async def claude_agent_turn(
    obs_dict: dict,
    valid_actions_dict: list[dict],
    agent_id: str,
) -> dict:
    """Run the model/tool loop until Claude returns an action."""
    messages = [{"role": "user", "content": build_prompt(obs_dict, valid_actions_dict)}]

    await workflow.execute_activity(ensure_memory_root, agent_id)

    while True:
        step = await workflow.execute_activity(
            claude_step,
            args=[agent_id, messages],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if step["type"] == "action":
            return step["action"]

        tool_call = step["tool_call"]
        tool_result = await execute_memory_tool(agent_id, tool_call)
        messages.append(step["assistant_message"])
        messages.append({
            "role": "user",
            "content": make_tool_result(tool_call["id"], tool_result),
        })


async def execute_memory_tool(agent_id: str, tool_call: dict) -> dict | str | None:
    """Map Claude's memory tool call to the corresponding Temporal activity."""
    if tool_call["name"] == "memory_list":
        return await workflow.execute_activity(memory_list, args=[agent_id, tool_call["path"]])
    if tool_call["name"] == "memory_read":
        return await workflow.execute_activity(memory_read, args=[agent_id, tool_call["path"]])
    if tool_call["name"] == "memory_write":
        return await workflow.execute_activity(
            memory_write,
            args=[agent_id, tool_call["path"], tool_call["content"]],
        )
    if tool_call["name"] == "memory_edit":
        return await workflow.execute_activity(
            memory_edit,
            args=[agent_id, tool_call["path"], tool_call["patch"]],
        )
    raise ValueError(f"Unknown memory tool: {tool_call['name']}")
```

Target file: `activities/agent.py`

```python
@activity.defn
async def claude_step(agent_id: str, messages: list[dict]) -> dict:
    """Call Claude once. Return either a poker action or a requested tool call."""
    client = anthropic.AsyncAnthropic()
    memory_path = f"memory/agents/{agent_id}"

    response = await client.messages.create(
        model="claude-opus-4-7-20250506",
        max_tokens=2048,
        system=build_system_prompt(memory_path),
        tools=memory_tools(),
        messages=messages,
    )

    return parse_action_or_tool_call(response)
```

```python
def build_system_prompt(memory_root: str) -> str:
    return f"""You are a poker agent. Your objective is to get better at poker
by playing and observing games.

You have a persistent file-system memory rooted at:
{memory_root}

Memory is not preloaded into your context. Use tools to explore it when useful:
- memory_list: list files and directories under your memory root
- memory_read: read a specific memory file
- memory_write: create or replace a memory file
- memory_edit: apply targeted edits to an existing memory file

Use memory to:
- Track opponent tendencies
- Record strategic learnings
- Note mistakes and adjustments
- Build your own mental model over time

If your memory is empty, first define your memory structure by writing
SYSTEM_PROMPT.md and any initial files you need. Prefer targeted edits for
incremental updates so you preserve useful context already in the file.

For your poker action, respond with: ACTION: fold|check_or_call|raise <amount>"""
```

---

## Memory Tool Activities

Target file: `activities/agent_memory.py`

Memory access is implemented as activities rather than direct workflow I/O. The
workflow runs the Claude tool loop: a model-call activity asks for a tool, the
workflow executes the matching memory activity, and the next model-call activity
receives the tool result.

```python
@activity.defn
async def ensure_memory_root(agent_id: str) -> None:
    """Create memory/agents/{agent_id}/ if this is the first run."""
    agent_memory_root(agent_id).mkdir(parents=True, exist_ok=True)


@activity.defn
async def memory_list(agent_id: str, path: str = ".") -> list[dict]:
    """List files and directories under memory/agents/{agent_id}/path."""
    root = agent_memory_root(agent_id)
    target = safe_join(root, path)
    return [
        {
            "path": os.path.relpath(entry.path, root),
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        }
        for entry in os.scandir(target)
    ]


@activity.defn
async def memory_read(agent_id: str, path: str) -> str:
    """Read one memory file. The model asks for only the files it needs."""
    root = agent_memory_root(agent_id)
    return Path(safe_join(root, path)).read_text()


@activity.defn
async def memory_write(agent_id: str, path: str, content: str) -> None:
    """Create or replace one memory file."""
    root = agent_memory_root(agent_id)
    target = Path(safe_join(root, path))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


@activity.defn
async def memory_edit(agent_id: str, path: str, patch: str) -> None:
    """Apply a targeted model-authored edit to one memory file.

    The patch can use the same style of structured file edit a coding model is
    already good at producing: find/replace hunks, append blocks, or a unified
    diff. The activity validates the target path, applies the edit, and fails
    cleanly if the patch does not match the current file.
    """
    root = agent_memory_root(agent_id)
    target = Path(safe_join(root, path))
    original = target.read_text()
    updated = apply_model_patch(original, patch)
    target.write_text(updated)
```

The model can therefore use its natural file-editing ability without being
trusted with arbitrary filesystem access. Every operation is scoped to
`memory/agents/{agent_id}/`, logged as an activity result, and available for
retry/error handling.

---

## Memory Access Flow

```
  Hand Starts
       │
       ▼
  Claude sees obs + memory tool descriptions
       │
       ▼
  Claude lists/reads only relevant memory files
       │
       ▼
  Claude decides action + optionally writes or edits memory
       │
       ├──► Action applied to game
       │
       └──► Memory activities persist writes/targeted edits
                │
                ▼
  Next decision: Claude can inspect the updated filesystem memory

  Hand Ends
       │
       ▼
  Post-hand reflection:
  Claude sees final result + full hand history
  Uses memory tools to update strategy notes, opponent reads, and mistakes
```

---

## Post-Hand Reflection Flow

Target file: `workflows/agent.py`

```python
async def claude_reflect(
    hand_result: dict,
    full_history: list[dict],
    agent_id: str,
) -> None:
    """After a hand, let Claude inspect and update memory."""
    prompt = f"""The hand just completed. Here's what happened:

Result: {"Won" if hand_result["payoff"] > 0 else "Lost"} {abs(hand_result["payoff"])} chips
Final board: {hand_result["board"]}
Your hand: {hand_result["hole_cards"]}
Opponent hand: {hand_result.get("opponent_cards", "unknown (mucked)")}

Full action history:
{format_history(full_history)}

Reflect on this hand. Update your memory with any learnings:
- Did you make any mistakes?
- What did you learn about your opponent?
- Any strategic adjustments for next time?

Use memory_list and memory_read to inspect relevant notes. Use memory_write for
new files and memory_edit for targeted updates to existing files."""

    messages = [{"role": "user", "content": prompt}]

    while True:
        step = await workflow.execute_activity(
            claude_step,
            args=[agent_id, messages],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if step["type"] == "done":
            return

        tool_call = step["tool_call"]
        tool_result = await execute_memory_tool(agent_id, tool_call)
        messages.append(step["assistant_message"])
        messages.append({
            "role": "user",
            "content": make_tool_result(tool_call["id"], tool_result),
        })
```

---

## Why File System

| Alternative | Why FS is better for this demo |
|-------------|--------------------------------|
| Database | Overkill; agent cannot define its own schema easily |
| Vector store | Good for retrieval but agent cannot browse or organize files naturally |
| In-memory dict | Lost on restart; not inspectable |
| **File system** | Agent reads/writes naturally; human can inspect; persists; agent defines structure |

---

## Demo Impact

During the talk:

- Show the empty `memory/agents/` folder
- Start the first game; Claude bootstraps its own memory structure
- After 5-10 hands, run `ls memory/agents/{agent_id}`
- Open a file like `opponent_models/human_player_0.md`
- Explain that the agent is writing its own playbook in real time, with no schema defined by the application
