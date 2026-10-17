"""Seed PostgreSQL with a simulated demo run.

Usage: uv run python scripts/seed_db.py [run-name] [seconds]
Requires DATABASE_URL (see .env.example); start Postgres with
``docker compose up -d``.
"""

import sys

from track_team import db
from track_team.engine import Simulation
from track_team.formations import SLOTS


def main() -> None:
    """Simulate, then insert the run in one transaction (idempotent by name)."""
    name = sys.argv[1] if len(sys.argv) > 1 else "demo-65s"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 65.0
    sim = Simulation(seed=7)
    sim.run_demo()
    frames = [sim.step(0.1).model_dump(mode="json") for _ in range(int(seconds / 0.1))]
    meta = {
        "seed": 7,
        "dt_s": 0.1,
        "duration_s": seconds,
        "field_m": {"length": 105.0, "width": 68.0},
        "sensor_corners": [
            {"x": 0.0, "y": 0.0},
            {"x": 105.0, "y": 0.0},
            {"x": 0.0, "y": 68.0},
            {"x": 105.0, "y": 68.0},
        ],
        "formation": "4-4-2 diamond",
    }
    slots = [
        {"id": s.id, "role": s.role, "group": s.group, "x": s.x, "y": s.y}
        for s in SLOTS
    ]
    with db.connect() as conn:
        run_id = db.seed_run(
            conn, name=name, seed=7, meta=meta, slots=slots, frames=frames
        )
    print(f"seeded run '{name}' id={run_id} frames={len(frames)}")


if __name__ == "__main__":
    main()
