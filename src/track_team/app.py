"""FastAPI transport: REST controls plus a ~10 Hz WebSocket position stream."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from track_team import db
from track_team.engine import Simulation
from track_team.match_stats import compute_match_stats
from track_team.models import Frame, MatchStats, Phase

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(psycopg.OperationalError)
def database_unreachable(_request: Request, _exc: Exception) -> JSONResponse:
    """Answer 503 (with CORS headers) instead of a bare 500 when Postgres is down.

    Lets pages fall back to JSON files when running without Docker.
    """
    return JSONResponse(status_code=503, content={"detail": "database not reachable"})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/runs")
def runs() -> list[dict[str, Any]]:
    """List recorded runs available for replay."""
    with db.connect() as conn:
        return db.list_runs(conn)


@app.get("/runs/{run_id}")
def run_detail(run_id: int) -> dict[str, Any]:
    """Return one run's metadata, slots and frame count."""
    with db.connect() as conn:
        detail = db.get_run(conn, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@app.get("/runs/{run_id}/frames")
def run_frames(run_id: int, from_idx: int = 0, limit: int = 100) -> dict[str, Any]:
    """Return a chunk of replay frames (default 100 = 10 s at 10 fps)."""
    with db.connect() as conn:
        if db.get_run(conn, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        frames = db.get_frames(
            conn, run_id, from_idx=max(0, from_idx), limit=max(1, min(limit, 500))
        )
    return {"run_id": run_id, "from_idx": max(0, from_idx), "frames": frames}


@app.get("/runs/{run_id}/stats")
def run_stats(run_id: int) -> MatchStats:
    """Return per-player match statistics computed over every frame of a run."""
    with db.connect() as conn:
        detail = db.get_run(conn, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="run not found")
        frames = db.get_frames(
            conn, run_id, from_idx=0, limit=max(1, int(detail["frame_count"]))
        )
    trace = {"meta": detail["meta"], "slots": detail["slots"], "frames": frames}
    try:
        return compute_match_stats(trace, run_id=run_id, name=detail["name"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/stats")
def upload_stats(trace: dict[str, Any]) -> MatchStats:
    """Return match statistics for an uploaded export JSON (not stored)."""
    try:
        return compute_match_stats(trace, run_id=None, name="upload")
    except (ValueError, KeyError, TypeError) as exc:
        detail = f"invalid match JSON: {exc}"
        raise HTTPException(status_code=422, detail=detail) from exc


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
