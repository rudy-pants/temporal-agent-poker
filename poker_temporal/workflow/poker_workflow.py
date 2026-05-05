from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError
from pokerkit import Automation, Mode, NoLimitTexasHoldem

from .types import Action, ActionRecord, Observation, SessionState

AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
    Automation.RUNOUT_COUNT_SELECTION,
)

STREET_NAMES = ["preflop", "flop", "turn", "river"]

TURN_TIMEOUT = timedelta(seconds=30)
MAX_INVALID_ATTEMPTS = 3
GPT_PLAYER_INDEX = 1


@workflow.defn(sandboxed=False)
class PokerGameWorkflow:
    def __init__(self):
        self.state = None
        self.action_queue: list[tuple[int, dict]] = []
        self.history: list[dict] = []
        self.saved_hole_cards: list[list[str]] = []
        self.memory_log: list[dict] = []
        self._session_state: SessionState | None = None

    @workflow.run
    async def run(self, config: dict, session: dict | None = None) -> dict:
        session_state = SessionState.from_dict(session) if session else None
        self._session_state = session_state

        starting_stacks = (
            tuple(session_state.stacks)
            if session_state
            else tuple(config["starting_stack"] for _ in range(config["player_count"]))
        )

        rng_seed = workflow.random().randint(0, 2**32)
        random.seed(rng_seed)

        self.state = NoLimitTexasHoldem.create_state(
            automations=AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes={-1: 0},
            raw_blinds_or_straddles=(
                config["small_blind"],
                config["big_blind"],
            ),
            min_bet=config["big_blind"],
            raw_starting_stacks=starting_stacks,
            player_count=config["player_count"],
            mode=Mode.CASH_GAME,
        )

        # Save hole cards immediately — PokerKit's HAND_KILLING clears loser's cards
        self.saved_hole_cards = [
            [repr(c) for c in hand] for hand in self.state.hole_cards
        ]

        while self.state.status:
            actor = self.state.actor_index
            if actor is None:
                break

            if actor == GPT_PLAYER_INDEX:
                await self._gpt_turn(actor)
            else:
                await self._human_turn(actor)

        # Wait briefly so clients can query the terminal state before workflow completes
        await workflow.sleep(5)

        result = {
            "payoffs": list(self.state.payoffs),
            "stacks": list(self.state.stacks),
        }

        # Reflect on this hand (lightweight — updates running notes, no filesystem)
        from .activities import gpt_reflect_hand, gpt_compress_learnings

        hand_result = {
            "hand_number": session_state.hand_number if session_state else 1,
            "payoff": self.state.payoffs[GPT_PLAYER_INDEX],
            "board_cards": [repr(c) for b in self.state.board_cards for c in b],
            "hole_cards": self.saved_hole_cards[GPT_PLAYER_INDEX] if GPT_PLAYER_INDEX < len(self.saved_hole_cards) else [],
            "opponent_cards": self.saved_hole_cards[0] if len(self.saved_hole_cards) > 0 else [],
        }
        current_notes = session_state.running_notes if session_state else ""

        try:
            updated_notes = await workflow.execute_activity(
                gpt_reflect_hand,
                args=[hand_result, self.history, current_notes],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:
            updated_notes = current_notes

        # Continue to next hand if both players have chips
        hand_number = session_state.hand_number if session_state else 1
        if all(s > 0 for s in self.state.stacks) and hand_number < 200:
            new_session = SessionState(
                stacks=list(self.state.stacks),
                hand_number=hand_number + 1,
                dealer_position=((session_state.dealer_position if session_state else 0) + 1) % config["player_count"],
                running_notes=updated_notes,
            )
            workflow.continue_as_new(args=[config, new_session.to_dict()])
        else:
            # Game over — compress learnings into persistent memory
            session_summary = {
                "hands_played": hand_number,
                "net_profit": self.state.payoffs[GPT_PLAYER_INDEX],
                "final_stacks": list(self.state.stacks),
            }
            try:
                await workflow.execute_activity(
                    gpt_compress_learnings,
                    args=[updated_notes, session_summary, "gpt-default"],
                    start_to_close_timeout=timedelta(seconds=20),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            except Exception:
                workflow.logger.warning("Failed to compress learnings")

        return result

    @workflow.signal
    def player_action(self, player_index: int, action_dict: dict):
        if self.state and self.state.status and self.state.actor_index == player_index:
            self.action_queue.append((player_index, action_dict))
        else:
            workflow.logger.warning(
                f"Rejected out-of-turn action from player {player_index}"
            )

    @workflow.query
    def get_observation(self, player_index: int) -> dict:
        return self._build_observation(player_index).to_dict()

    @workflow.query
    def valid_actions(self, player_index: int) -> list[dict]:
        if not self.state or not self.state.status:
            return []
        if self.state.actor_index != player_index:
            return []

        actions = [
            Action("fold").to_dict(),
            Action("check_or_call").to_dict(),
        ]

        if self.state.can_complete_bet_or_raise_to():
            min_raise = self.state.min_completion_betting_or_raising_to_amount
            max_raise = self.state.max_completion_betting_or_raising_to_amount
            actions.append(Action("raise", min_raise).to_dict())
            if max_raise > min_raise:
                actions.append(Action("raise", max_raise).to_dict())

        return actions

    @workflow.query
    def debug_state(self) -> dict:
        if not self.state:
            return {"status": "not_initialized"}
        return {
            "actor_index": self.state.actor_index,
            "street_index": self.state.street_index,
            "status": self.state.status,
            "stacks": list(self.state.stacks),
            "bets": list(self.state.bets),
            "pot": self.state.total_pot_amount,
            "action_queue_size": len(self.action_queue),
            "history_size": len(self.history),
            "board_cards": [repr(c) for b in self.state.board_cards for c in b],
            "hole_cards": [
                [repr(c) for c in hand] for hand in self.state.hole_cards
            ],
        }

    @workflow.query
    def get_memory_log(self) -> list[dict]:
        return self.memory_log

    async def _human_turn(self, actor: int):
        attempts = 0
        while True:
            try:
                await workflow.wait_condition(
                    lambda: self._has_action_from(actor),
                    timeout=TURN_TIMEOUT,
                )
            except asyncio.TimeoutError:
                self._apply_action(actor, Action("fold"))
                workflow.logger.info(f"Player {actor} timed out, auto-folded")
                return

            action_dict = self._pop_action_from(actor)
            action = Action.from_dict(action_dict)
            if self._apply_action(actor, action):
                return

            attempts += 1
            if attempts >= MAX_INVALID_ATTEMPTS:
                self._apply_action(actor, Action("fold"))
                workflow.logger.info(f"Player {actor} exceeded invalid attempts, auto-folded")
                return

    async def _gpt_turn(self, actor: int):
        from .activities import gpt_decide

        obs_dict = self._build_observation(actor).to_dict()
        valid_dict = self.valid_actions(actor)
        running_notes = self._session_state.running_notes if self._session_state else ""

        try:
            result = await workflow.execute_activity(
                gpt_decide,
                args=[obs_dict, valid_dict, "gpt-default", running_notes],
                start_to_close_timeout=timedelta(seconds=20),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            # Track memory changes
            memory_updates = result.pop("_memory_updates", [])
            if memory_updates:
                self.memory_log.append({
                    "hand_number": len(self.history),
                    "street": STREET_NAMES[self.state.street_index] if self.state.street_index is not None else "showdown",
                    "updates": memory_updates,
                })
            action = Action.from_dict(result)
        except (ActivityError, Exception):
            action = Action("check_or_call")
            workflow.logger.warning("GPT activity failed, defaulting to check/call")

        if not self._apply_action(actor, action):
            self._apply_action(actor, Action("check_or_call"))

    def _apply_action(self, player_index: int, action: Action) -> bool:
        street_idx = self.state.street_index
        street_name = STREET_NAMES[street_idx] if street_idx is not None else "showdown"

        try:
            if action.type == "fold":
                self.state.fold()
            elif action.type == "check_or_call":
                self.state.check_or_call()
            elif action.type == "raise":
                amount = action.amount
                min_r = self.state.min_completion_betting_or_raising_to_amount
                max_r = self.state.max_completion_betting_or_raising_to_amount
                amount = max(min_r, min(amount, max_r))
                self.state.complete_bet_or_raise_to(amount)
        except (ValueError, IndexError) as e:
            workflow.logger.warning(f"Invalid action from player {player_index}: {action} ({e})")
            return False

        self.history.append(ActionRecord(
            player_index=player_index,
            action=action,
            street=street_name,
        ).to_dict())
        return True

    def _build_observation(self, player_index: int) -> Observation:
        if not self.state:
            return Observation(player_index=player_index)

        street_idx = self.state.street_index
        street_name = STREET_NAMES[street_idx] if street_idx is not None else "showdown"

        hole_cards = []
        if self.state.hole_cards and player_index < len(self.state.hole_cards):
            hole_cards = [repr(c) for c in self.state.hole_cards[player_index]]

        board_cards = [repr(c) for b in self.state.board_cards for c in b]

        actor = self.state.actor_index
        min_raise = 0
        max_raise = 0
        current_bet = 0
        if actor == player_index and self.state.status:
            current_bet = max(self.state.bets) - self.state.bets[player_index]
            if self.state.can_complete_bet_or_raise_to():
                min_raise = self.state.min_completion_betting_or_raising_to_amount
                max_raise = self.state.max_completion_betting_or_raising_to_amount

        active_players = [i for i, s in enumerate(self.state.statuses) if s]

        # When hand is over, reveal all cards from saved snapshot
        opponent_cards = []
        if not self.state.status:
            opponent_index = 1 - player_index
            if opponent_index < len(self.saved_hole_cards):
                opponent_cards = self.saved_hole_cards[opponent_index]

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
            opponent_cards=opponent_cards,
        )

    def _has_action_from(self, actor: int) -> bool:
        return any(pi == actor for pi, _ in self.action_queue)

    def _pop_action_from(self, actor: int) -> dict:
        for i, (pi, action_dict) in enumerate(self.action_queue):
            if pi == actor:
                self.action_queue.pop(i)
                return action_dict
        return Action("fold").to_dict()

    def _should_continue(self, session: SessionState) -> bool:
        return all(s > 0 for s in self.state.stacks) and session.hand_number < 200
