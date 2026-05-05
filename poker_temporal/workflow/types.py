from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class Action:
    type: Literal["fold", "check_or_call", "raise"]
    amount: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Action:
        return cls(type=d["type"], amount=d.get("amount", 0))


@dataclass
class ActionRecord:
    player_index: int
    action: Action
    street: str

    def to_dict(self) -> dict:
        return {
            "player_index": self.player_index,
            "action": self.action.to_dict(),
            "street": self.street,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ActionRecord:
        return cls(
            player_index=d["player_index"],
            action=Action.from_dict(d["action"]),
            street=d["street"],
        )


@dataclass
class Observation:
    hole_cards: list[str] = field(default_factory=list)
    board_cards: list[str] = field(default_factory=list)
    pot: int = 0
    stacks: list[int] = field(default_factory=list)
    current_bet: int = 0
    min_raise: int = 0
    max_raise: int = 0
    player_index: int = 0
    actor_index: int | None = None
    is_my_turn: bool = False
    street: str = "preflop"
    active_players: list[int] = field(default_factory=list)
    history: list = field(default_factory=list)
    terminal: bool = False
    payoff: int = 0
    opponent_cards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hole_cards": self.hole_cards,
            "board_cards": self.board_cards,
            "pot": self.pot,
            "stacks": self.stacks,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "max_raise": self.max_raise,
            "player_index": self.player_index,
            "actor_index": self.actor_index,
            "is_my_turn": self.is_my_turn,
            "street": self.street,
            "active_players": self.active_players,
            "history": [h if isinstance(h, dict) else h.to_dict() for h in self.history],
            "terminal": self.terminal,
            "payoff": self.payoff,
            "opponent_cards": self.opponent_cards,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Observation:
        return cls(
            hole_cards=d.get("hole_cards", []),
            board_cards=d.get("board_cards", []),
            pot=d.get("pot", 0),
            stacks=d.get("stacks", []),
            current_bet=d.get("current_bet", 0),
            min_raise=d.get("min_raise", 0),
            max_raise=d.get("max_raise", 0),
            player_index=d.get("player_index", 0),
            actor_index=d.get("actor_index"),
            is_my_turn=d.get("is_my_turn", False),
            street=d.get("street", "preflop"),
            active_players=d.get("active_players", []),
            history=[ActionRecord.from_dict(h) for h in d.get("history", [])],
            terminal=d.get("terminal", False),
            payoff=d.get("payoff", 0),
        )


@dataclass
class SessionState:
    stacks: list[int] = field(default_factory=list)
    hand_number: int = 1
    dealer_position: int = 0
    running_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SessionState:
        return cls(
            stacks=d.get("stacks", []),
            hand_number=d.get("hand_number", 1),
            dealer_position=d.get("dealer_position", 0),
            running_notes=d.get("running_notes", ""),
        )
