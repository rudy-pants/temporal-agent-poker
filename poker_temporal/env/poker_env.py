from __future__ import annotations

import asyncio
from uuid import uuid4

from temporalio.client import Client

from workflow.poker_workflow import PokerGameWorkflow
from workflow.types import Action, Observation


class PokerEnv:
    """Gym-compatible async wrapper around the Temporal poker workflow."""

    def __init__(self, client: Client, player_index: int):
        self.client = client
        self.player_index = player_index
        self.handle = None

    async def reset(self, game_id: str | None = None, config: dict | None = None) -> Observation:
        config = config or {
            "small_blind": 1,
            "big_blind": 2,
            "starting_stack": 200,
            "player_count": 2,
        }
        gid = game_id or f"poker-{uuid4()}"
        self.handle = await self.client.start_workflow(
            PokerGameWorkflow.run,
            args=[config, None],
            id=gid,
            task_queue="poker",
        )
        return await self._wait_for_turn()

    async def step(self, action: Action) -> tuple[Observation, int, bool, dict]:
        await self.handle.signal(
            PokerGameWorkflow.player_action,
            args=[self.player_index, action.to_dict()],
        )
        obs = await self._wait_for_turn()
        return obs, obs.payoff, obs.terminal, {"street": obs.street}

    async def action_space(self) -> list[dict]:
        return await self.handle.query(
            PokerGameWorkflow.valid_actions,
            arg=self.player_index,
        )

    async def observe(self) -> Observation:
        obs_dict = await self.handle.query(
            PokerGameWorkflow.get_observation,
            arg=self.player_index,
        )
        return Observation.from_dict(obs_dict)

    async def _wait_for_turn(self) -> Observation:
        delay = 0.1
        max_delay = 2.0
        while True:
            obs = await self.observe()
            if obs.is_my_turn or obs.terminal:
                return obs
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, max_delay)
