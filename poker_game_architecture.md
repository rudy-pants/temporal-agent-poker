# Multiplayer Poker with Temporal + PokerKit + Gym Interface

## Goal

Build a turn-based poker game where:
- **Player 1**: Human (CLI/web interface)
- **Player 2**: AI agent (Claude Opus 4.7)

Using **PokerKit** as the authoritative game engine, **Temporal** for workflow orchestration, and an **OpenAI Gym-style interface** for both players.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Local Development Host                           │
│                                                                             │
│  ┌────────────────────────┐        ┌─────────────────────────────────────┐  │
│  │ Frontend Client        │        │ FastAPI / WebSocket Server          │  │
│  │ frontend/              │◄──────►│ server/                             │  │
│  │ - React poker table    │        │ - Starts games                      │  │
│  │ - Human actions        │        │ - Sends Temporal signals            │  │
│  │ - Live event log       │        │ - Queries observations              │  │
│  └────────────────────────┘        └──────────────────┬──────────────────┘  │
│                                                        │                     │
│                                                        │ Temporal client     │
│                                                        ▼                     │
│  ┌────────────────────────┐        ┌─────────────────────────────────────┐  │
│  │ Temporal Dev Server    │◄──────►│ Temporal Worker                     │  │
│  │ localhost:7233         │        │ worker.py                           │  │
│  │ - Durable event log    │        │ - Registers workflows/              │  │
│  │ - Timers               │        │ - Registers activities/             │  │
│  │ - Workflow state       │        │ - Runs PokerKit + agent module      │  │
│  └────────────────────────┘        └──────────────────┬──────────────────┘  │
│                                                        │                     │
│                          ┌─────────────────────────────┼──────────────────┐  │
│                          │                             │                  │  │
│                          ▼                             ▼                  │  │
│              ┌──────────────────────┐      ┌───────────────────────────┐  │  │
│              │ workflows/           │      │ activities/               │  │  │
│              │ - PokerGameWorkflow  │      │ - Claude model calls      │  │  │
│              │ - Agent turn hooks   │      │ - Memory file operations  │  │  │
│              │ - Signals / queries  │      │ - External side effects   │  │  │
│              └──────────┬───────────┘      └─────────────┬─────────────┘  │  │
│                         │                                │                │  │
│                         ▼                                ▼                │  │
│              ┌──────────────────────┐      ┌───────────────────────────┐  │  │
│              │ PokerKit State       │      │ Agent Memory              │  │  │
│              │ - Deck / streets     │      │ memory/agents/{agent_id}/ │  │  │
│              │ - Pot math           │      │ - Files explored by tools │  │  │
│              │ - Hand evaluation    │      │ - Reads, writes, edits    │  │  │
│              └──────────────────────┘      └───────────────────────────┘  │  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Module Responsibilities

| Module | Location | Responsibility |
|--------|----------|----------------|
| Temporal dev server | local process | Durable workflow history, timers, replay, and task queues |
| Temporal worker | `worker.py` | Registers every workflow from `workflows/` and every activity from `activities/` |
| Game workflows | `workflows/` | Authoritative game orchestration, signals, queries, turn timers, and agent module hooks |
| Activities | `activities/` | External effects: Claude calls, memory filesystem operations, server notifications |
| Frontend client | `frontend/` | Human gameplay UI, live state display, action submission |
| WebSocket server | `server/` | Browser bridge to Temporal signals and queries |
| Agent module | `workflows/agent.py`, `activities/agent.py`, `activities/agent_memory.py` | Claude decisions, tool loop, resilience, and memory; see [agent_architecture.md](agent_architecture.md) |

### Code Placement Rule

All Temporal workflow code described in these architecture files belongs under
`workflows/`. All Temporal activity code belongs under `activities/`. Workflow
helpers may call activities, but filesystem I/O, model API calls, notifications,
and other side effects must remain activities.

---

## What Temporal Provides

Temporal is the **game server** — it holds authoritative state, serializes access, and makes the game durable. Without it, you'd need a database + message queue + crash recovery + timer infrastructure, all wired together manually.

| Problem                         | Temporal Solution                          | Without Temporal                                  |
|---------------------------------|--------------------------------------------|---------------------------------------------------|
| Two players act simultaneously  | Single workflow = single-threaded state machine. Signals queue, no race conditions | Locks, database transactions, check-and-set logic |
| Server crashes mid-hand         | Workflow replays from event history automatically. Players reconnect and continue | Custom persistence + recovery code                |
| Player disconnects / goes AFK   | `workflow.wait_condition` with timeout → auto-fold in one line. Timer is durable (fires even after worker restart) | Separate timer service + dead-letter handling     |
| Audit trail of every hand       | Every signal is recorded in Temporal's event history — full ordered replay log for free | Custom event sourcing / append-only log table     |
| Multi-hand sessions grow memory | Continue-as-new: carry stack sizes into a fresh execution, bounded memory | Manual state checkpointing + cleanup              |
| Observing game state            | Queries return instant reads without blocking the game loop | Separate read replica or cache layer              |

**What Temporal does NOT do here:**
- Poker rules → PokerKit
- AI decision-making → Claude
- Player-facing interface → CLI/web layer

```
┌─────────────────────────────────────────────────────────────────┐
│                    Responsibility Boundaries                     │
├─────────────────┬──────────────────────┬────────────────────────┤
│   PokerKit      │     Temporal         │   Agents / UI          │
├─────────────────┼──────────────────────┼────────────────────────┤
│ Shuffle & deal  │ Durable state        │ Human CLI input        │
│ Betting rules   │ Turn serialization   │ Claude API calls       │
│ Pot math        │ Crash recovery       │ Display / rendering    │
│ Hand evaluation │ Turn timers          │ Action parsing         │
│ Street logic    │ Event history        │ Session management     │
│ Showdown        │ Continue-as-new      │                        │
└─────────────────┴──────────────────────┴────────────────────────┘
```

---

## Why PokerKit

PokerKit replaces the entire custom `engine/` module:

| Custom Code (before)       | PokerKit (now)                            |
|----------------------------|-------------------------------------------|
| `cards.py` (Card, Deck)    | `state.deck_cards`, `state.deal_hole()`   |
| `game_state.py` (rules)   | `NoLimitTexasHoldem.create_state()`       |
| `evaluator.py` (rankings) | `state.get_hand()`, automatic evaluation  |
| Pot splitting logic        | `state.pots`, `Automation.CHIPS_PUSHING`  |
| Street advancement         | `state.street_index`, automations         |
| Action validation          | `state.actor_index`, built-in validation  |

---

## PokerKit State Lifecycle

```python
from pokerkit import Automation, Mode, NoLimitTexasHoldem

state = NoLimitTexasHoldem.create_state(
    automations=(
        Automation.ANTE_POSTING,
        Automation.BLIND_OR_STRADDLE_POSTING,
        Automation.CARD_BURNING,
        Automation.HOLE_DEALING,
        Automation.BOARD_DEALING,
        Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
        Automation.HAND_KILLING,
        Automation.CHIPS_PUSHING,
        Automation.CHIPS_PULLING,
    ),
    ante_trimming_status=True,
    raw_antes={-1: 0},
    raw_blinds_or_straddles=(1, 2),
    min_bet=2,
    raw_starting_stacks=(200, 200),
    player_count=2,
    mode=Mode.CASH_GAME,
)

# After create_state with full automations:
# - Antes posted automatically
# - Blinds posted automatically
# - Hole cards dealt automatically
# State is now ready for player actions (preflop betting)

# Player actions:
state.check_or_call()              # current actor checks/calls
state.complete_bet_or_raise_to(6)  # current actor raises to 6
state.fold()                       # current actor folds

# After all betting on a street completes:
# - Cards burned automatically
# - Board cards dealt automatically
# - Next street begins

# After final street or all-but-one fold:
# - Hands evaluated automatically
# - Chips pushed/pulled automatically
# - state.status becomes False (hand complete)
```

---

## Data Types

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class Observation:
    hole_cards: list[str]           # player's private cards e.g. ["Ah", "Kd"]
    board_cards: list[str]          # community cards e.g. ["Ts", "7c", "2h"]
    pot: int                        # total pot
    stacks: list[int]              # all player chip counts (by seat index)
    current_bet: int               # amount to call
    min_raise: int                 # minimum raise-to amount
    max_raise: int                 # maximum raise-to (all-in)
    player_index: int              # this player's seat (0 or 1)
    actor_index: int | None        # who must act now (None if hand over)
    is_my_turn: bool
    street: str                    # "preflop" | "flop" | "turn" | "river"
    active_players: list[int]      # indices of non-folded players
    history: list[ActionRecord]    # actions this hand
    terminal: bool                 # hand over?
    payoff: int                    # chips won/lost this hand (0 until terminal)

@dataclass
class Action:
    type: Literal["fold", "check_or_call", "raise"]
    amount: int = 0               # raise-to amount (only for raise)

@dataclass
class ActionRecord:
    player_index: int
    action: Action
    street: str
```

---

## Temporal Primitives Mapping

| Game Concept             | Temporal Feature                |
|--------------------------|--------------------------------|
| Player action            | **Signal** (player_action)     |
| Game state query         | **Query** (get_observation)    |
| Turn timer / disconnect  | **Workflow timer** (30s)       |
| Hand complete            | **Workflow completion**        |
| Next hand (session)      | **Continue-as-new**            |
| Multi-hand session state | **Continue-as-new** carry-over |

---

## Temporal Workflow

Target file: `workflows/poker_game.py`

```python
import pickle
from temporalio import workflow
from pokerkit import Automation, Mode, NoLimitTexasHoldem

AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)

STREET_NAMES = ["preflop", "flop", "turn", "river"]


@workflow.defn
class PokerGameWorkflow:
    def __init__(self):
        self.state = None
        self.action_queue: list[tuple[int, Action]] = []
        self.history: list[ActionRecord] = []

    @workflow.run
    async def run(self, config: dict):
        self.state = NoLimitTexasHoldem.create_state(
            automations=AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes={-1: 0},
            raw_blinds_or_straddles=(
                config["small_blind"],
                config["big_blind"],
            ),
            min_bet=config["big_blind"],
            raw_starting_stacks=tuple(
                config["starting_stack"] for _ in range(config["player_count"])
            ),
            player_count=config["player_count"],
            mode=Mode.CASH_GAME,
        )

        # Main game loop: wait for actions until hand completes
        while self.state.status:
            actor = self.state.actor_index

            if actor is None:
                # No actor needed (automations handle everything)
                break

            # Wait for the current actor to submit an action
            await workflow.wait_condition(
                lambda: self._has_action_from(actor)
            )

            action = self._pop_action_from(actor)
            self._apply_action(actor, action)

        # Return final payoffs
        return {
            "payoffs": list(self.state.payoffs),
            "stacks": list(self.state.stacks),
        }

    @workflow.signal
    def player_action(self, player_index: int, action: Action):
        self.action_queue.append((player_index, action))

    @workflow.query
    def get_observation(self, player_index: int) -> Observation:
        street_idx = self.state.street_index
        street_name = STREET_NAMES[street_idx] if street_idx is not None else "showdown"

        # Get this player's hole cards (only their own)
        hole_cards = []
        if self.state.hole_cards and player_index < len(self.state.hole_cards):
            hole_cards = [str(c) for c in self.state.hole_cards[player_index]]

        # Community cards (flatten board_cards)
        board_cards = []
        for board in self.state.board_cards:
            board_cards.extend(str(c) for c in board)

        # Determine min/max raise
        actor = self.state.actor_index
        min_raise = 0
        max_raise = 0
        current_bet = 0
        if actor == player_index and self.state.status:
            current_bet = max(self.state.bets) - self.state.bets[player_index]
            min_raise = self._get_min_raise()
            max_raise = self.state.stacks[player_index] + self.state.bets[player_index]

        active_players = [
            i for i, s in enumerate(self.state.statuses) if s
        ]

        return Observation(
            hole_cards=hole_cards,
            board_cards=board_cards,
            pot=self.state.total_pot_amount,
            stacks=list(self.state.stacks),
            current_bet=current_bet,
            min_raise=min_raise,
            max_raise=max_raise,
            player_index=player_index,
            actor_index=actor,
            is_my_turn=(actor == player_index),
            street=street_name,
            active_players=active_players,
            history=self.history,
            terminal=not self.state.status,
            payoff=self.state.payoffs[player_index] if not self.state.status else 0,
        )

    @workflow.query
    def valid_actions(self, player_index: int) -> list[Action]:
        if self.state.actor_index != player_index or not self.state.status:
            return []

        actions = [Action("fold"), Action("check_or_call")]

        min_raise = self._get_min_raise()
        max_raise = self.state.stacks[player_index] + self.state.bets[player_index]
        if min_raise > 0 and max_raise >= min_raise:
            actions.append(Action("raise", min_raise))  # min raise
            if max_raise > min_raise:
                actions.append(Action("raise", max_raise))  # all-in

        return actions

    def _apply_action(self, player_index: int, action: Action):
        street_idx = self.state.street_index
        street_name = STREET_NAMES[street_idx] if street_idx is not None else "showdown"

        if action.type == "fold":
            self.state.fold()
        elif action.type == "check_or_call":
            self.state.check_or_call()
        elif action.type == "raise":
            self.state.complete_bet_or_raise_to(action.amount)

        self.history.append(ActionRecord(
            player_index=player_index,
            action=action,
            street=street_name,
        ))

    def _has_action_from(self, actor: int) -> bool:
        return any(pi == actor for pi, _ in self.action_queue)

    def _pop_action_from(self, actor: int) -> Action:
        for i, (pi, action) in enumerate(self.action_queue):
            if pi == actor:
                self.action_queue.pop(i)
                return action

    def _get_min_raise(self) -> int:
        # PokerKit tracks completion/raise amounts internally
        # min raise = last raise size + current bet level
        # Simplified: use big blind as minimum increment
        max_bet = max(self.state.bets)
        return max_bet + self.state.min_completion_raising_to_amount
```

---

## PokerEnv (Gym Wrapper)

```python
import asyncio
from uuid import uuid4
from temporalio.client import Client


class PokerEnv:
    """Gym-compatible async wrapper around the Temporal poker workflow."""

    def __init__(self, client: Client, player_index: int):
        self.client = client
        self.player_index = player_index
        self.handle = None

    async def reset(self, game_id: str = None, config: dict = None) -> Observation:
        config = config or {
            "small_blind": 1,
            "big_blind": 2,
            "starting_stack": 200,
            "player_count": 2,
        }
        self.handle = await self.client.start_workflow(
            PokerGameWorkflow.run,
            args=[config],
            id=game_id or f"poker-{uuid4()}",
            task_queue="poker",
        )
        return await self._wait_for_turn()

    async def step(self, action: Action) -> tuple[Observation, int, bool, dict]:
        await self.handle.signal(
            PokerGameWorkflow.player_action,
            args=[self.player_index, action],
        )
        obs = await self._wait_for_turn()
        return obs, obs.payoff, obs.terminal, {"street": obs.street}

    async def action_space(self) -> list[Action]:
        return await self.handle.query(
            PokerGameWorkflow.valid_actions,
            arg=self.player_index,
        )

    async def observe(self) -> Observation:
        return await self.handle.query(
            PokerGameWorkflow.get_observation,
            arg=self.player_index,
        )

    async def _wait_for_turn(self) -> Observation:
        while True:
            obs = await self.observe()
            if obs.is_my_turn or obs.terminal:
                return obs
            await asyncio.sleep(0.05)
```

---

## Agent Module

The AI player is a separate architecture module. It owns Claude prompts, model
calls, action parsing, retry/fallback behavior, memory tool loops, and persistent
filesystem memory under `memory/agents/{agent_id}/`.

All agent code and detailed agent architecture live in
[agent_architecture.md](agent_architecture.md).

---

## Human Player (CLI)

```python
class HumanPlayer:
    """CLI interface for human player."""

    def __init__(self, player_index: int):
        self.player_index = player_index

    async def act(self, obs: Observation, valid_actions: list[Action]) -> Action:
        print(f"\n{'='*50}")
        print(f"  Street: {obs.street}")
        print(f"  Your hand: {' '.join(obs.hole_cards)}")
        print(f"  Board: {' '.join(obs.board_cards) or '(none)'}")
        print(f"  Pot: {obs.pot}")
        print(f"  Your stack: {obs.stacks[self.player_index]}")
        print(f"  To call: {obs.current_bet}")
        print(f"\n  Actions:")
        print(f"    f = fold")
        print(f"    c = check/call")
        if obs.min_raise > 0:
            print(f"    r <amount> = raise (min {obs.min_raise}, max {obs.max_raise})")
        print(f"{'='*50}")

        while True:
            choice = input("  > ").strip().lower()
            if choice == "f":
                return Action("fold")
            elif choice == "c":
                return Action("check_or_call")
            elif choice.startswith("r"):
                parts = choice.split()
                if len(parts) == 2:
                    try:
                        amount = int(parts[1])
                        if obs.min_raise <= amount <= obs.max_raise:
                            return Action("raise", amount)
                        print(f"    Amount must be between {obs.min_raise} and {obs.max_raise}")
                    except ValueError:
                        pass
                else:
                    return Action("raise", obs.min_raise)
            print("    Invalid input. Use: f, c, or r <amount>")
```

---

## Game Loop (Orchestrator)

```python
import asyncio
from temporalio.client import Client


async def main():
    client = await Client.connect("localhost:7233")

    human_env = PokerEnv(client, player_index=0)
    human = HumanPlayer(player_index=0)

    session_stacks = [200, 200]

    while True:
        # Start a new hand
        game_id = f"poker-{uuid4()}"
        config = {
            "small_blind": 1,
            "big_blind": 2,
            "starting_stack": 200,
            "player_count": 2,
        }

        obs = await human_env.reset(game_id=game_id, config=config)

        while not obs.terminal:
            if obs.is_my_turn:
                valid = await human_env.action_space()
                action = await human.act(obs, valid)
                obs, reward, done, info = await human_env.step(action)
            else:
                # AI turns are handled inside the workflow through the agent module.
                obs = await human_env.observe()

        # Hand complete
        final = await human_env.observe()
        print(f"\n  Hand over! Your result: {'+' if final.payoff > 0 else ''}{final.payoff}")
        print(f"  Stacks: You={final.stacks[0]}, Claude={final.stacks[1]}")

        if input("\n  Play another hand? (y/n): ").strip().lower() != "y":
            break


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Temporal Replay & Determinism

PokerKit with full automations is **deterministic given the same deck order**. Temporal replays work because:

1. The deck is shuffled once at state creation (inside the workflow, using `workflow.random()`)
2. All player actions come in via signals (recorded in event history)
3. Automations (dealing, evaluation) are pure functions of state + deck order
4. On replay, same deck + same signals = same state transitions

**Important**: Replace Python's `random` with Temporal's deterministic RNG:

```python
# PokerKit uses random internally for deck shuffling.
# For Temporal determinism, seed it with workflow.random():
import random
random.seed(workflow.random().randint(0, 2**32))

# Then create_state() will produce the same deck on replay
```

**Open question**: Verify whether PokerKit automations call `random` *after* initial state creation (e.g., when dealing board cards on new streets). If they do, the seed must be set before every automation trigger, or PokerKit must be patched to accept an external RNG.

---

## Design Gaps & Mitigations

### 1. Out-of-Turn Action Rejection

**Problem**: The signal handler blindly queues any action. If Claude sends an action while the workflow waits for the human, that stale action sits in the queue and gets applied immediately on Claude's next turn — before Claude sees the updated board.

**Fix**: Reject actions in the signal handler unless it's that player's turn.

```python
@workflow.signal
def player_action(self, player_index: int, action: Action):
    if self.state.status and self.state.actor_index == player_index:
        self.action_queue.append((player_index, action))
    else:
        workflow.logger.warning(
            f"Rejected out-of-turn action from player {player_index}"
        )
```

---

### 2. PokerKit State Serialization

**Problem**: Temporal persists workflow state via serialization. PokerKit's `State` is a complex object with methods, iterators, and internal references — it won't JSON-serialize.

**Options**:

| Approach               | Pros                          | Cons                              |
|------------------------|-------------------------------|-----------------------------------|
| Action replay          | No serialization needed; Temporal replays signals naturally | Replay must re-seed RNG identically |
| Pickle Data Converter  | Simple, works with any object | Fragile across PokerKit versions  |
| Explicit state mapping | Version-safe, inspectable     | Significant implementation effort |

**Chosen approach**: Action replay. The workflow never needs to serialize the PokerKit state — Temporal's replay mechanism reconstructs it by re-executing the workflow code with the same signals from event history. This works because:
- The RNG is seeded deterministically via `workflow.random()` before state creation
- All player inputs arrive as signals (recorded in history)
- Automations are pure functions of game state

**Constraint**: The workflow code + PokerKit version must remain compatible across replays. Pin `pokerkit` to an exact version in production.

---

### 3. Turn Timeout Implementation

**Problem**: If Claude's API hangs or the human walks away, the game is stuck forever.

**Fix**: Race `wait_condition` against a timer. Auto-fold on timeout.

```python
@workflow.run
async def run(self, config: dict):
    TURN_TIMEOUT = timedelta(seconds=30)

    self.state = NoLimitTexasHoldem.create_state(...)

    while self.state.status:
        actor = self.state.actor_index
        if actor is None:
            break

        # Race: player action vs timeout
        action_received = workflow.wait_condition(
            lambda: self._has_action_from(actor)
        )

        timed_out = False
        try:
            await asyncio.wait_for(action_received, timeout=None)
            # Use Temporal timer instead of asyncio timeout:
            await workflow.wait_condition(
                lambda: self._has_action_from(actor),
                timeout=TURN_TIMEOUT,
            )
        except asyncio.TimeoutError:
            timed_out = True

        if timed_out:
            # Auto-fold on timeout
            self._apply_action(actor, Action("fold"))
            workflow.logger.info(f"Player {actor} timed out, auto-folded")
        else:
            action = self._pop_action_from(actor)
            self._apply_action(actor, action)

    return {"payoffs": list(self.state.payoffs), "stacks": list(self.state.stacks)}
```

---

### 4. Invalid Action Handling

**Problem**: Claude might return an illegal raise amount or malformed action. PokerKit will throw an exception, crashing the workflow permanently.

**Fix**: Wrap action application in try/except. On invalid action, re-wait for a valid one (with a retry limit before auto-fold).

```python
MAX_INVALID_ATTEMPTS = 3

def _apply_action(self, player_index: int, action: Action) -> bool:
    """Apply action. Returns True on success, False if invalid."""
    street_idx = self.state.street_index
    street_name = STREET_NAMES[street_idx] if street_idx is not None else "showdown"

    try:
        if action.type == "fold":
            self.state.fold()
        elif action.type == "check_or_call":
            self.state.check_or_call()
        elif action.type == "raise":
            amount = action.amount
            # Clamp to valid range
            min_r = self._get_min_raise()
            max_r = self.state.stacks[player_index] + self.state.bets[player_index]
            amount = max(min_r, min(amount, max_r))
            self.state.complete_bet_or_raise_to(amount)
    except (ValueError, IndexError) as e:
        workflow.logger.warning(f"Invalid action from player {player_index}: {action} ({e})")
        return False

    self.history.append(ActionRecord(
        player_index=player_index,
        action=action,
        street=street_name,
    ))
    return True
```

In the main loop:
```python
attempts = 0
while True:
    await workflow.wait_condition(
        lambda: self._has_action_from(actor),
        timeout=TURN_TIMEOUT,
    )
    action = self._pop_action_from(actor)
    if self._apply_action(actor, action):
        break
    attempts += 1
    if attempts >= MAX_INVALID_ATTEMPTS:
        self._apply_action(actor, Action("fold"))
        break
```

---

### 5. Continue-as-New for Multi-Hand Sessions

**Problem**: Temporal workflow history grows with every event. After many hands, it exceeds Temporal's 50K event limit and the workflow dies.

**Fix**: Each workflow execution plays exactly ONE hand. Multi-hand sessions use continue-as-new.

```python
@dataclass
class SessionState:
    stacks: list[int]
    hand_number: int
    dealer_position: int  # rotates each hand

@workflow.run
async def run(self, config: dict, session: SessionState = None):
    session = session or SessionState(
        stacks=[config["starting_stack"]] * config["player_count"],
        hand_number=1,
        dealer_position=0,
    )

    # ... play one hand using session.stacks as starting stacks ...

    # After hand completes, continue to next hand
    if self._should_continue(session):
        new_session = SessionState(
            stacks=list(self.state.stacks),
            hand_number=session.hand_number + 1,
            dealer_position=(session.dealer_position + 1) % config["player_count"],
        )
        workflow.continue_as_new(args=[config, new_session])

    return {"payoffs": list(self.state.payoffs), "stacks": list(self.state.stacks)}

def _should_continue(self, session: SessionState) -> bool:
    # Stop if a player is busted or hit hand limit
    return all(s > 0 for s in self.state.stacks) and session.hand_number < 200
```

---

### 6. Client Polling Replacement

**Problem**: `_wait_for_turn()` polls every 50ms, hammering the Temporal frontend with queries.

**Options**:

| Approach                  | Latency | Complexity | Best For       |
|---------------------------|---------|------------|----------------|
| Poll with backoff         | ~200ms  | Low        | CLI prototype  |
| Signal-back via activity  | ~50ms   | Medium     | Web UI (push)  |
| Temporal Update (SDK 1.4) | ~10ms   | Low        | If SDK supports|

**For CLI (v1)**: Exponential backoff polling is acceptable.

```python
async def _wait_for_turn(self) -> Observation:
    delay = 0.1  # start at 100ms
    max_delay = 2.0
    while True:
        obs = await self.observe()
        if obs.is_my_turn or obs.terminal:
            return obs
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, max_delay)
```

**For Web UI (v2)**: The workflow signals a notification activity when the actor changes, which pushes an event over WebSocket to the waiting client.

---

### 7. Agent Resilience

**Problem**: The model API can timeout, return 500s, or produce unparseable
responses.

**Fix**: Agent retry, validation, and fallback behavior belongs in
[agent_architecture.md](agent_architecture.md), not in the poker workflow.

---

### 8. Observability & Debugging

**Problem**: No way to inspect internal state when a game appears "stuck."

**Fix**: Add diagnostic queries to the workflow.

```python
@workflow.query
def debug_state(self) -> dict:
    """Full internal state for debugging. Not exposed to players."""
    return {
        "actor_index": self.state.actor_index,
        "street_index": self.state.street_index,
        "status": self.state.status,
        "stacks": list(self.state.stacks),
        "bets": list(self.state.bets),
        "pot": self.state.total_pot_amount,
        "action_queue_size": len(self.action_queue),
        "history_size": len(self.history),
        "board_cards": [str(c) for b in self.state.board_cards for c in b],
        "all_hole_cards": [
            [str(c) for c in hand] for hand in self.state.hole_cards
        ],
    }
```

Query it via CLI: `temporal workflow query --workflow-id poker-xxx --query-type debug_state`

---

### Summary of Gaps Addressed

| Gap                        | Severity | Status       |
|----------------------------|----------|--------------|
| Out-of-turn action queuing | Critical | Fixed above  |
| PokerKit serialization     | Critical | Solved via action replay |
| Turn timeouts              | Critical | Implemented  |
| Invalid action crashes     | Critical | Try/except + fallback |
| Unbounded history          | Critical | Continue-as-new per hand |
| Client polling overhead    | Medium   | Backoff (v1), push (v2) |
| Claude API failures        | Medium   | Retry + fallback |
| Debugging stuck games      | Medium   | Debug query  |
| PokerKit RNG on replay     | Medium   | Needs verification |

---

## Web UI (Demo Interface)

### Overview

A single-page React app connected to a FastAPI backend via WebSocket. Designed for live demos — the audience sees cards dealt, Claude "thinking", and real-time game progression.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BROWSER                                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         POKER TABLE                                    │  │
│  │                                                                        │  │
│  │          ┌─────────┐                        ┌─────────┐               │  │
│  │          │ Claude   │                        │  Pot:   │               │  │
│  │          │ 🂠 🂠     │                        │  $42    │               │  │
│  │          │ Stack:198│                        └─────────┘               │  │
│  │          └─────────┘                                                   │  │
│  │                                                                        │  │
│  │                    ┌─────────────────────┐                            │  │
│  │                    │  🂡  🂸  🃉  🂣  ___  │  ← Community Cards         │  │
│  │                    └─────────────────────┘                            │  │
│  │                                                                        │  │
│  │          ┌─────────┐                                                   │  │
│  │          │  You     │                                                  │  │
│  │          │ A♠  K♦   │                                                  │  │
│  │          │ Stack:196│                                                  │  │
│  │          └─────────┘                                                   │  │
│  │                                                                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐              │  │
│  │  │   FOLD   │  │  CALL $4 │  │  RAISE  [____] [$6-196]│              │  │
│  │  └──────────┘  └──────────┘  └────────────────────────┘              │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  EVENT LOG (Temporal Events)                              [LIVE ●]     │  │
│  │                                                                        │  │
│  │  12:03:01  Workflow started (poker-a3f2)                              │  │
│  │  12:03:01  Signal: blinds posted (1/2)                                │  │
│  │  12:03:01  Hole cards dealt                                           │  │
│  │  12:03:03  Signal: player_action(0, raise 6)                          │  │
│  │  12:03:04  Signal: player_action(1, check_or_call)  ← Claude          │  │
│  │  12:03:04  Flop dealt: [A♠ 8♣ 9♦]                                    │  │
│  │  ▼ streaming...                                                       │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Architecture with Web UI

```
┌───────────┐         WebSocket          ┌──────────────────┐
│  Browser  │◄══════════════════════════►│  FastAPI Server  │
│  (React)  │  { obs, events, actions }  │                  │
└───────────┘                            └────────┬─────────┘
                                                  │
                                    Temporal Client│(signals, queries)
                                                  │
                              ┌────────────────────▼────────────────────┐
                              │         Temporal Workflow               │
                              │         (PokerKit State)                │
                              └────────────────────┬───────────────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │  Agent Module   │
                                          │  (Activities)   │
                                          └─────────────────┘
```

Key change: the AI player runs through the **Agent Module** invoked by the
workflow, not as an external client. The workflow controls turn order and
timeouts; agent implementation details live in
[agent_architecture.md](agent_architecture.md).

---

### FastAPI Backend (WebSocket Bridge)

```python
from fastapi import FastAPI, WebSocket
from temporalio.client import Client
import asyncio
import json

app = FastAPI()


@app.websocket("/ws/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    await websocket.accept()
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(game_id)

    # Start background task: push state updates to browser
    async def push_updates():
        last_history_len = 0
        while True:
            try:
                obs = await handle.query(
                    PokerGameWorkflow.get_observation, arg=0
                )
                # Only push when state changes
                msg = {
                    "type": "state_update",
                    "observation": obs_to_dict(obs),
                }
                await websocket.send_json(msg)

                if obs.terminal:
                    await websocket.send_json({"type": "hand_complete", "payoff": obs.payoff})
                    break

                await asyncio.sleep(0.2)
            except Exception:
                break

    push_task = asyncio.create_task(push_updates())

    # Receive actions from the browser
    try:
        while True:
            data = await websocket.receive_json()
            if data["type"] == "action":
                action = Action(
                    type=data["action_type"],
                    amount=data.get("amount", 0),
                )
                await handle.signal(
                    PokerGameWorkflow.player_action,
                    args=[0, action],
                )
    except Exception:
        push_task.cancel()


@app.post("/api/new-game")
async def new_game():
    client = await Client.connect("localhost:7233")
    game_id = f"poker-{uuid4()}"
    config = {
        "small_blind": 1,
        "big_blind": 2,
        "starting_stack": 200,
        "player_count": 2,
    }
    handle = await client.start_workflow(
        PokerGameWorkflow.run,
        args=[config],
        id=game_id,
        task_queue="poker",
    )
    return {"game_id": game_id}


def obs_to_dict(obs: Observation) -> dict:
    return {
        "hole_cards": obs.hole_cards,
        "board_cards": obs.board_cards,
        "pot": obs.pot,
        "stacks": obs.stacks,
        "current_bet": obs.current_bet,
        "min_raise": obs.min_raise,
        "max_raise": obs.max_raise,
        "is_my_turn": obs.is_my_turn,
        "street": obs.street,
        "active_players": obs.active_players,
        "terminal": obs.terminal,
        "payoff": obs.payoff,
    }
```

---

### Agent Integration

The workflow invokes the agent module when the AI seat is the current actor. All
Claude-specific activity code, prompts, action parsing, memory tools, retries,
and fallbacks are specified in [agent_architecture.md](agent_architecture.md).

---

### React Frontend (Key Components)

```
frontend/
├── src/
│   ├── App.tsx                 # WebSocket connection + game state
│   ├── components/
│   │   ├── PokerTable.tsx      # Table layout, community cards
│   │   ├── PlayerHand.tsx      # Hole cards display
│   │   ├── OpponentHand.tsx    # Face-down cards for Claude
│   │   ├── ActionPanel.tsx     # Fold/Call/Raise buttons + slider
│   │   ├── PotDisplay.tsx      # Pot amount, side pots
│   │   ├── EventLog.tsx        # Temporal event stream panel
│   │   ├── Card.tsx            # Single card with suit/rank styling
│   │   └── ChipStack.tsx       # Visual chip count
│   ├── hooks/
│   │   └── useGameSocket.ts    # WebSocket hook managing connection
│   ├── types.ts                # Observation, Action types
│   └── styles/
│       └── table.css           # Green felt, card styles
├── package.json
└── vite.config.ts
```

---

### WebSocket Hook (Client Side)

```typescript
// hooks/useGameSocket.ts
import { useState, useEffect, useCallback, useRef } from "react";

interface GameState {
  observation: Observation | null;
  connected: boolean;
  events: GameEvent[];
}

export function useGameSocket(gameId: string) {
  const [state, setState] = useState<GameState>({
    observation: null,
    connected: false,
    events: [],
  });
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(`ws://localhost:8000/ws/game/${gameId}`);
    ws.current = socket;

    socket.onopen = () => setState((s) => ({ ...s, connected: true }));

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "state_update") {
        setState((s) => ({
          ...s,
          observation: msg.observation,
          events: [...s.events, { time: new Date(), ...msg }],
        }));
      }
    };

    socket.onclose = () => setState((s) => ({ ...s, connected: false }));

    return () => socket.close();
  }, [gameId]);

  const sendAction = useCallback((type: string, amount?: number) => {
    ws.current?.send(JSON.stringify({ type: "action", action_type: type, amount }));
  }, []);

  return { ...state, sendAction };
}
```

---

### Action Panel Component

```typescript
// components/ActionPanel.tsx
interface Props {
  observation: Observation;
  onAction: (type: string, amount?: number) => void;
}

export function ActionPanel({ observation, onAction }: Props) {
  const [raiseAmount, setRaiseAmount] = useState(observation.min_raise);
  const { is_my_turn, current_bet, min_raise, max_raise } = observation;

  if (!is_my_turn) {
    return <div className="action-panel waiting">Waiting for Claude...</div>;
  }

  return (
    <div className="action-panel">
      <button className="btn-fold" onClick={() => onAction("fold")}>
        Fold
      </button>

      <button className="btn-call" onClick={() => onAction("check_or_call")}>
        {current_bet > 0 ? `Call $${current_bet}` : "Check"}
      </button>

      {min_raise > 0 && (
        <div className="raise-group">
          <input
            type="range"
            min={min_raise}
            max={max_raise}
            value={raiseAmount}
            onChange={(e) => setRaiseAmount(Number(e.target.value))}
          />
          <button
            className="btn-raise"
            onClick={() => onAction("raise", raiseAmount)}
          >
            Raise to ${raiseAmount}
          </button>
        </div>
      )}
    </div>
  );
}
```

---

### Demo Features (Conference Impact)

| Feature                     | Why it matters for the demo                         |
|-----------------------------|-----------------------------------------------------|
| Live event log panel        | Shows Temporal events streaming in real-time        |
| Claude "thinking" indicator | Spinner while activity runs, shows AI deliberation  |
| Card deal animations        | CSS transitions on new cards appearing              |
| Workflow ID visible         | Audience can see it's a real Temporal workflow       |
| "Kill worker" button        | Demo durability: kill worker, restart, game resumes |
| Side-by-side Temporal UI    | Show Temporal Web alongside game for event history  |

---

### Demo Script (for the talk)

1. Open browser → start new game
2. Play a few hands normally, showing cards + actions
3. Point out the event log: "Every action is a Temporal signal"
4. **Kill the worker process mid-hand** → show game is "paused"
5. Restart worker → game resumes exactly where it left off
6. Open Temporal Web UI → show the full event history, replay
7. "This is 200 lines of game logic, zero persistence code"

---

## Project Structure

```
poker_temporal/
├── workflows/
│   ├── __init__.py
│   ├── poker_game.py          # PokerGameWorkflow wrapping PokerKit
│   ├── agent.py               # Agent turn + reflection workflow helpers
│   └── types.py               # Observation, Action, ActionRecord
├── activities/
│   ├── __init__.py
│   ├── agent.py               # Claude model-call activities
│   ├── agent_memory.py        # Memory list/read/write/edit activities
│   └── notifications.py       # Optional UI notification activities
├── env/
│   ├── __init__.py
│   └── poker_env.py           # Gym-like async wrapper (CLI mode)
├── server/
│   ├── __init__.py
│   ├── app.py                 # FastAPI + WebSocket bridge
│   └── routes.py              # REST endpoints (new game, etc.)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── PokerTable.tsx
│   │   │   ├── PlayerHand.tsx
│   │   │   ├── OpponentHand.tsx
│   │   │   ├── ActionPanel.tsx
│   │   │   ├── PotDisplay.tsx
│   │   │   ├── EventLog.tsx
│   │   │   ├── Card.tsx
│   │   │   └── ChipStack.tsx
│   │   ├── hooks/
│   │   │   └── useGameSocket.ts
│   │   ├── types.ts
│   │   └── styles/
│   │       └── table.css
│   ├── package.json
│   └── vite.config.ts
├── worker.py                  # Temporal worker process
├── main.py                    # CLI game orchestrator (fallback)
└── requirements.txt
```

The worker imports workflow definitions only from `workflows/` and activity
definitions only from `activities/`. New Temporal code should follow that split
even when an architecture section shows a compact snippet.

---

## Dependencies

```
# Backend
temporalio>=1.7.0
anthropic>=0.40.0
pokerkit>=0.5.0
fastapi>=0.110.0
uvicorn>=0.27.0
websockets>=12.0

# Frontend (package.json)
react, react-dom, vite, typescript
```

---

## Running Locally

```bash
# Terminal 1: Temporal dev server
temporal server start-dev

# Terminal 2: Worker (registers workflows + activities)
python worker.py

# Terminal 3: FastAPI backend
uvicorn server.app:app --reload --port 8000

# Terminal 4: React frontend
cd frontend && npm run dev

# Open http://localhost:5173
```

---

## Why This Design

| Concern                    | Solution                                              |
|----------------------------|-------------------------------------------------------|
| Correct poker rules        | PokerKit (99% test coverage, battle-tested)           |
| No custom card/eval code   | PokerKit automations handle all mechanical actions    |
| Durability                 | Temporal workflow survives crashes mid-hand            |
| Turn timers                | Temporal cancellable timers (auto-fold on timeout)    |
| Full replay                | Temporal event history + deterministic PokerKit       |
| Clean player interface     | Gym-style env hides Temporal signals/queries          |
| Extensible variants        | Swap `NoLimitTexasHoldem` for any PokerKit variant    |
