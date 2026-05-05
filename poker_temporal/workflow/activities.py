from __future__ import annotations

import os
import re

from temporalio import activity
from openai import AsyncOpenAI

MEMORY_BASE_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "agents")


@activity.defn
async def gpt_decide(obs_dict: dict, valid_actions_dict: list[dict], agent_id: str, running_notes: str = "") -> dict:
    activity.logger.info(f"GPT deciding for agent {agent_id}...")
    client = AsyncOpenAI()
    memory_path = os.path.join(MEMORY_BASE_PATH, agent_id)
    memory_context = load_memory(memory_path)
    system = build_system_prompt(memory_context, running_notes)

    prompt = build_decision_prompt(obs_dict, valid_actions_dict)
    activity.logger.info(f"Calling OpenAI API (model={os.environ.get('GPT_MODEL', 'gpt-4o')})...")

    try:
        response = await client.chat.completions.create(
            model=os.environ.get("GPT_MODEL", "gpt-4o"),
            max_tokens=512,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        activity.logger.info(f"GPT response: {text[:100]}")
    except Exception as e:
        activity.logger.warning(f"OpenAI API error: {e}")
        return {"type": "check_or_call", "amount": 0}

    action = parse_action(text, valid_actions_dict)

    memory_updates = parse_memory_updates(text)
    if memory_updates:
        apply_memory_updates(memory_path, memory_updates)
        activity.logger.info(f"Memory updated: {[path for path, _ in memory_updates]}")

    return {
        **action,
        "_memory_updates": [
            {"path": path, "content": content} for path, content in memory_updates
        ] if memory_updates else [],
    }


@activity.defn
async def gpt_reflect_hand(hand_result: dict, full_history: list[dict], running_notes: str) -> str:
    """Lightweight per-hand reflection. Returns updated running notes (no filesystem writes)."""
    client = AsyncOpenAI()

    prompt = f"""Hand #{hand_result.get("hand_number", "?")} just completed.

Result: {"Won" if hand_result["payoff"] > 0 else "Lost"} {abs(hand_result["payoff"])} chips
Final board: {hand_result.get("board_cards", [])}
Your hand: {hand_result.get("hole_cards", [])}
Opponent hand: {hand_result.get("opponent_cards", "unknown (mucked)")}

Action history:
{format_history(full_history)}

Your current running notes on this opponent:
---
{running_notes or "(empty - first hand)"}
---

Update your running notes. Focus on:
- Opponent tendencies (aggressive? passive? bluffs? calls too much?)
- Patterns you notice (bet sizing tells, position-dependent behavior)
- Adjustments you should make next hand

Keep notes concise (under 500 words). Output ONLY the updated notes, nothing else."""

    try:
        response = await client.chat.completions.create(
            model=os.environ.get("GPT_MODEL", "gpt-4o"),
            max_tokens=600,
            messages=[
                {
                    "role": "system",
                    "content": "You are a poker player keeping running notes on your opponent during a session. Be concise and actionable.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or running_notes
    except Exception:
        return running_notes


@activity.defn
async def gpt_compress_learnings(running_notes: str, session_summary: dict, agent_id: str) -> None:
    """End-of-game compression. Distills running notes into compact learnings, writes to filesystem."""
    client = AsyncOpenAI()
    memory_path = os.path.join(MEMORY_BASE_PATH, agent_id)
    memory_context = load_memory(memory_path)

    prompt = f"""A poker session just ended.

Session summary:
- Hands played: {session_summary.get("hands_played", "?")}
- Final result: {"Won" if session_summary["net_profit"] > 0 else "Lost"} {abs(session_summary["net_profit"])} chips
- Final stacks: You={session_summary["final_stacks"][1]}, Opponent={session_summary["final_stacks"][0]}

Your running notes from this session:
---
{running_notes}
---

Your existing memory:
---
{memory_context}
---

Compress what you learned into your persistent memory. Write concise, general learnings that will help in future sessions against any opponent (not just this one). Also save a brief opponent profile if their style was distinctive.

Output memory updates as <memory_update> blocks:
<memory_update>
WRITE path/to/file.md
content
</memory_update>

Suggested structure:
- strategy.md: update with new strategic insights
- opponents/session_notes.md: brief profile of this opponent
- learnings.md: general poker learnings from this session

Be selective — only write what's genuinely useful for future play."""

    try:
        response = await client.chat.completions.create(
            model=os.environ.get("GPT_MODEL", "gpt-4o"),
            max_tokens=1500,
            messages=[
                {
                    "role": "system",
                    "content": "You are a poker player saving compressed learnings after a session. Be concise and actionable. Only save what matters.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
    except Exception:
        return

    updates = parse_memory_updates(text)
    if updates:
        apply_memory_updates(memory_path, updates)
        activity.logger.info(f"Compressed learnings saved: {[p for p, _ in updates]}")


def load_memory(path: str) -> str:
    if not os.path.exists(path) or not os.listdir(path):
        return "MEMORY_EMPTY: Define your memory structure on your first decision."

    context_parts = []
    total_size = 0
    max_size = 50_000

    for root, _, files in os.walk(path):
        for f in sorted(files):
            filepath = os.path.join(root, f)
            rel_path = os.path.relpath(filepath, path)
            try:
                content = open(filepath).read()
            except (IOError, UnicodeDecodeError):
                continue
            total_size += len(content)
            if total_size > max_size:
                context_parts.append(f"[{rel_path}]\n(truncated - memory limit reached)")
                break
            context_parts.append(f"[{rel_path}]\n{content}")
        if total_size > max_size:
            break

    return "\n---\n".join(context_parts)


def build_system_prompt(memory_context: str, running_notes: str = "") -> str:
    notes_section = ""
    if running_notes:
        notes_section = f"""

Your live session notes on the current opponent:
<session_notes>
{running_notes}
</session_notes>

Use these notes to exploit opponent tendencies."""

    return f"""You are an aggressive, skilled poker player. You play to WIN, not to survive.

IMPORTANT RULES FOR YOUR RESPONSES:
- You MUST respond with ACTION: followed by your choice
- Valid actions: fold | check_or_call | raise <amount>
- Do NOT fold unless you have a truly terrible hand AND face a large bet
- With any decent hand, CALL or RAISE
- Be aggressive: raise with good hands, call with mediocre ones, only fold garbage facing big bets

Your persistent memory:

<memory>
{memory_context}
</memory>{notes_section}

After your ACTION line, you may optionally output memory updates:
<memory_update>
WRITE path/to/file.md
content here
</memory_update>

If your memory is empty, create initial strategy files after your first decision.

RESPOND WITH ACTION: first, then optional memory updates."""


def build_decision_prompt(obs_dict: dict, valid_actions_dict: list[dict]) -> str:
    history_str = ""
    for rec in obs_dict.get("history", [])[-10:]:
        action = rec.get("action", {})
        amt = f" to {action['amount']}" if action.get("amount") else ""
        history_str += f"  Player {rec['player_index']}: {action['type']}{amt} ({rec['street']})\n"

    valid_str = ", ".join(
        f"{a['type']}" + (f" {a['amount']}" if a.get("amount") else "")
        for a in valid_actions_dict
    )

    return f"""Current poker situation:

Your hand: {obs_dict['hole_cards']}
Community cards: {obs_dict['board_cards'] or 'None'}
Pot: {obs_dict['pot']}
Your stack: {obs_dict['stacks'][obs_dict['player_index']]}
Amount to call: {obs_dict['current_bet']}
Min raise to: {obs_dict['min_raise']}
Max raise to: {obs_dict['max_raise']}
Street: {obs_dict['street']}

Action history this hand:
{history_str or '  (none yet)'}

Valid actions: [{valid_str}]

ACTION:"""


def parse_action(text: str, valid_actions_dict: list[dict]) -> dict:
    action_match = re.search(r"ACTION:\s*(.*)", text, re.IGNORECASE)
    action_text = action_match.group(1).strip().lower() if action_match else text.strip().lower()

    if "fold" in action_text:
        return {"type": "fold", "amount": 0}
    elif "raise" in action_text:
        numbers = re.findall(r"\d+", action_text)
        if numbers:
            amount = int(numbers[0])
            return {"type": "raise", "amount": amount}
        raise_actions = [a for a in valid_actions_dict if a["type"] == "raise"]
        if raise_actions:
            return raise_actions[0]
        return {"type": "check_or_call", "amount": 0}
    else:
        return {"type": "check_or_call", "amount": 0}


def parse_memory_updates(text: str) -> list[tuple[str, str]]:
    updates = []
    pattern = r"<memory_update>\s*WRITE\s+(\S+)\s*\n(.*?)</memory_update>"
    matches = re.findall(pattern, text, re.DOTALL)
    for path, content in matches:
        updates.append((path.strip(), content.strip()))
    return updates


def apply_memory_updates(base_path: str, updates: list[tuple[str, str]]):
    os.makedirs(base_path, exist_ok=True)
    for rel_path, content in updates:
        rel_path = rel_path.lstrip("/")
        if ".." in rel_path:
            continue
        full_path = os.path.join(base_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)


def format_history(history: list[dict]) -> str:
    lines = []
    for rec in history:
        action = rec.get("action", {})
        amt = f" to {action.get('amount')}" if action.get("amount") else ""
        lines.append(f"  Player {rec['player_index']}: {action['type']}{amt} ({rec['street']})")
    return "\n".join(lines) if lines else "  (none)"
