"""FastAPI transport: REST controls plus a ~10 Hz WebSocket position stream."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from track_team.engine import Simulation
from track_team.models import Frame, Phase

sim = Simulation(seed=7)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the fixed-step simulation loop for the life of the server."""

    async def _loop() -> None:
        while True:
            sim.step(0.1)
            await asyncio.sleep(0.1)

    task = asyncio.create_task(_loop())
    yield
    task.cancel()


app = FastAPI(title="track-team player simulation", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/simulation/start")
def start() -> Frame:
    """Start moving from scattered positions into the 4-4-2 diamond."""
    sim.start()
    return sim.frame()


@app.post("/simulation/pause")
def pause() -> Frame:
    """Freeze the simulation in place."""
    sim.running = False
    return sim.frame()


@app.post("/simulation/resume")
def resume() -> Frame:
    """Resume a paused simulation."""
    sim.running = True
    return sim.frame()


@app.post("/simulation/reset")
def reset(seed: int = 7) -> Frame:
    """Return to wrong, scattered starting positions."""
    sim.reset(seed)
    return sim.frame()


@app.post("/simulation/run-demo")
def run_demo() -> Frame:
    """Start the hands-free sequence: scattered -> forming -> attack/defense."""
    sim.run_demo()
    return sim.frame()


@app.post("/simulation/scenario/{name}")
def scenario(name: Phase) -> Frame:
    """Switch scenario (`forming`, `attack` or `defense`)."""
    sim.set_phase(name)
    return sim.frame()


@app.get("/simulation/state")
def state() -> Frame:
    """Return the latest frame without advancing time."""
    return sim.frame()


@app.websocket("/ws/positions")
async def positions(websocket: WebSocket) -> None:
    """Stream frames: first one immediately, then ~10 Hz (AC-07)."""
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(sim.frame().model_dump(mode="json"))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
