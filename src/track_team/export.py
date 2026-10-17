"""Export a full demo run to a single JSON file for frontend/sensor teams."""

import json
from pathlib import Path

from track_team.engine import Simulation
from track_team.formations import SLOTS
from track_team.models import FIELD_LENGTH_M, FIELD_WIDTH_M, SENSOR_CORNERS


def write_trace(path: Path, *, seed: int = 7, seconds: float = 65.0) -> Path:
    """Simulate the demo sequence and write every frame to ``path`` as JSON.

    Args:
        path: Destination JSON file (parent directories are created).
        seed: Simulation seed; same seed gives the same trace.
        seconds: Simulated duration; 65 s covers scattered, forming,
            attack and defense.

    Returns:
        The path written.
    """
    sim = Simulation(seed=seed)
    sim.run_demo()
    frames = [sim.step(0.1).model_dump(mode="json") for _ in range(int(seconds / 0.1))]
    payload = {
        "meta": {
            "seed": seed,
            "dt_s": 0.1,
            "duration_s": seconds,
            "field_m": {"length": FIELD_LENGTH_M, "width": FIELD_WIDTH_M},
            "sensor_corners": [{"x": x, "y": y} for x, y in SENSOR_CORNERS],
            "formation": "4-4-2 diamond",
        },
        "slots": [
            {"id": s.id, "role": s.role, "group": s.group, "x": s.x, "y": s.y}
            for s in SLOTS
        ],
        "frames": frames,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path
