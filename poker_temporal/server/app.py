from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from temporalio.client import Client

from workflow.poker_workflow import PokerGameWorkflow
from workflow.types import Action

temporal_client: Client | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global temporal_client
    temporal_client = await Client.connect("localhost:7233")
    yield
    temporal_client = None


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/new-game")
async def new_game():
    game_id = f"poker-{uuid4()}"
    config = {
        "small_blind": 1,
        "big_blind": 2,
        "starting_stack": 200,
        "player_count": 2,
    }
    await temporal_client.start_workflow(
        PokerGameWorkflow.run,
        args=[config, None],
        id=game_id,
        task_queue="poker",
    )
    return {"game_id": game_id}


@app.get("/api/game/{game_id}/state")
async def get_state(game_id: str):
    handle = temporal_client.get_workflow_handle(game_id)
    obs = await handle.query(PokerGameWorkflow.get_observation, arg=0)
    return obs


@app.websocket("/ws/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    await websocket.accept()

    async def push_updates():
        last_obs_json = None
        retries = 0
        while True:
            try:
                handle = temporal_client.get_workflow_handle(game_id)
                obs = await handle.query(PokerGameWorkflow.get_observation, arg=0)
                import json
                obs_json = json.dumps(obs, sort_keys=True)
                if obs_json != last_obs_json:
                    last_obs_json = obs_json
                    await websocket.send_json({"type": "state_update", "observation": obs})
                    if obs.get("terminal"):
                        await websocket.send_json({
                            "type": "hand_complete",
                            "payoff": obs.get("payoff", 0),
                        })
                retries = 0
                await asyncio.sleep(0.3)
            except Exception:
                retries += 1
                if retries > 20:
                    return
                await asyncio.sleep(0.5)

    push_task = asyncio.create_task(push_updates())

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "action":
                action = Action(
                    type=data["action_type"],
                    amount=data.get("amount", 0),
                )
                handle = temporal_client.get_workflow_handle(game_id)
                await handle.signal(
                    PokerGameWorkflow.player_action,
                    args=[0, action.to_dict()],
                )
    except WebSocketDisconnect:
        pass
    finally:
        push_task.cancel()
