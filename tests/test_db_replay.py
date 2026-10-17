"""Integration checks for the PostgreSQL replay API (AC-13/AC-14).

Skipped when PostgreSQL is not reachable, so the suite stays green
without Docker; run `docker compose up -d` to enable them.
"""

import pytest
from fastapi.testclient import TestClient

from track_team import db
from track_team.app import app

_FRAME = {
    "t": 0.0,
    "phase": "scattered",
    "ball": {"x": 52.5, "y": 34.0},
    "players": [
        {
            "id": f"P{n}",
            "role": "GK" if n == 1 else "LS",
            "group": "GK" if n == 1 else "ATT",
            "x": float(n),
            "y": 34.0,
            "vx": 0.0,
            "vy": 0.0,
            "speed": 0.0,
            "distance_m": 0.0,
        }
        for n in range(1, 12)
    ],
    "metrics": {
        "formation_error_m": 10.0,
        "centroid": {"x": 6.0, "y": 34.0},
        "team_length_m": 10.0,
        "team_width_m": 0.0,
        "line_gap_def_mid_m": 0.0,
        "line_gap_mid_att_m": 0.0,
    },
}


@pytest.fixture(scope="module")
def run_id() -> int:
    try:
        conn = db.connect()
    except Exception:
        pytest.skip("PostgreSQL not reachable")
    with conn:
        seeded = db.seed_run(
            conn,
            name="test-run",
            seed=7,
            meta={"dt_s": 0.1, "field_m": {"length": 105.0, "width": 68.0}},
            slots=[],
            frames=[_FRAME, {**_FRAME, "t": 0.1}],
        )
    conn.close()
    return seeded


def test_ac13_seeded_run_is_listed_with_counts(run_id: int) -> None:
    with TestClient(app) as client:
        runs = client.get("/runs").json()
        detail = client.get(f"/runs/{run_id}").json()
    assert any(r["id"] == run_id and r["frame_count"] == 2 for r in runs)
    assert detail["frame_count"] == 2


def test_ac14_frames_chunk_shape_and_404(run_id: int) -> None:
    with TestClient(app) as client:
        chunk = client.get(f"/runs/{run_id}/frames", params={"from_idx": 0, "limit": 1})
        missing = client.get("/runs/999999/frames")
    assert chunk.status_code == 200
    frames = chunk.json()["frames"]
    assert len(frames) == 1
    assert len(frames[0]["players"]) == 11
    assert frames[0]["players"][0]["id"] == "P1"
    assert missing.status_code == 404
