"""Acceptance checks for docs/specs/player-match-stats.md (AC-01..AC-09).

The DB check (AC-09, run vs upload) is skipped when PostgreSQL is not
reachable, like tests/test_db_replay.py.
"""

import contextlib
import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from track_team import db
from track_team.app import app
from track_team.match_stats import compute_match_stats
from track_team.models import MatchStats

_TRACE_PATH = Path(__file__).parent.parent / "examples" / "simulation_trace.json"
_V_MAX = {"GK": 5.0, "DEF": 7.5, "MID": 8.0, "ATT": 9.0}


@pytest.fixture(scope="module")
def trace() -> dict[str, Any]:
    return json.loads(_TRACE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stats(trace: dict[str, Any]) -> MatchStats:
    return compute_match_stats(trace, run_id=None, name="example")


def _by_id(stats: MatchStats) -> dict[str, Any]:
    return {p.id: p for p in stats.players}


def test_ac01_eleven_players_and_duration(stats: MatchStats) -> None:
    assert len(stats.players) == 11
    assert stats.frames == 650
    assert stats.duration_s == pytest.approx(64.9, abs=0.01)
    assert [p.id for p in stats.players] == [f"P{n}" for n in range(1, 12)]


def test_ac02_distance_matches_last_frame(
    stats: MatchStats, trace: dict[str, Any]
) -> None:
    last = {p["id"]: p["distance_m"] for p in trace["frames"][-1]["players"]}
    for p in stats.players:
        assert p.distance_m == pytest.approx(last[p.id], abs=0.01)


def test_ac03_speeds_within_role_limits(stats: MatchStats) -> None:
    for p in stats.players:
        assert p.max_speed_mps <= _V_MAX[p.group]
        assert 0 < p.avg_speed_mps <= p.max_speed_mps


def test_ac04_passes_follow_attacking_pattern(stats: MatchStats) -> None:
    players = _by_id(stats)
    made = {pid: p.passes for pid, p in players.items() if p.passes}
    got = {pid: p.passes_received for pid, p in players.items() if p.passes_received}
    assert made == {"P6": 2, "P8": 2, "P9": 2, "P5": 2}
    assert got == {"P8": 2, "P9": 2, "P5": 2, "P11": 2}
    assert stats.team.passes == 8


def test_ac05_goals_credited_to_first_post_striker(stats: MatchStats) -> None:
    assert stats.team.goals == 2
    assert {p.id: p.goals for p in stats.players if p.goals} == {"P11": 2}


def test_ac06_saves_only_for_goalkeeper(stats: MatchStats) -> None:
    players = _by_id(stats)
    assert players["P1"].saves == 0
    assert all(p.saves is None for pid, p in players.items() if pid != "P1")


def test_invariants(stats: MatchStats, trace: dict[str, Any]) -> None:
    assert sum(p.passes for p in stats.players) == stats.team.passes
    assert sum(p.passes_received for p in stats.players) == stats.team.passes
    assert sum(p.goals for p in stats.players) <= stats.team.goals
    assert all(p.distance_m >= 0 for p in stats.players)
    assert compute_match_stats(trace, run_id=None, name="example") == stats


def _player(pid: str, group: str, x: float, y: float) -> dict[str, Any]:
    return {
        "id": pid,
        "role": group,
        "group": group,
        "x": x,
        "y": y,
        "vx": 0.0,
        "vy": 0.0,
        "speed": 0.0,
        "distance_m": 0.0,
    }


def _frames(
    phase: str, balls: list[tuple[float, float]], players: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "t": round(i * 0.1, 1),
            "phase": phase,
            "ball": {"x": x, "y": y},
            "players": players,
        }
        for i, (x, y) in enumerate(balls)
    ]


def test_ac07_synthetic_passes_ignore_brushed_teammate() -> None:
    players = [
        _player("P1", "GK", 5.0, 34.0),
        _player("P2", "MID", 10.0, 10.0),  # A
        _player("P3", "MID", 20.0, 10.5),  # brushed in flight
        _player("P4", "MID", 30.0, 10.0),  # B
    ]
    balls = (
        [(10.5, 10.0)] * 5  # A
        + [(19.5, 10.0), (20.5, 10.0)]  # in flight, 2 frames near P3
        + [(29.5, 10.0)] * 5  # B
        + [(10.5, 10.0)] * 5  # back to A
    )
    stats = _by_id(
        compute_match_stats(
            {"frames": _frames("attack", balls, players)}, run_id=None, name="t"
        )
    )
    assert (stats["P2"].passes, stats["P2"].passes_received) == (1, 1)
    assert (stats["P4"].passes, stats["P4"].passes_received) == (1, 1)
    assert (stats["P3"].passes, stats["P3"].passes_received) == (0, 0)


def _shot(keeper_y: float) -> dict[str, Any]:
    players = [_player("P1", "GK", 2.0, keeper_y), _player("P2", "DEF", 30.0, 60.0)]
    balls = [(40.0 - 2.0 * i, 34.0) for i in range(21)]  # 20 m/s towards x = 0
    return {"frames": _frames("defense", balls, players)}


def test_ac08_synthetic_save_and_conceded_shot() -> None:
    saved = compute_match_stats(_shot(keeper_y=34.0), run_id=None, name="t")
    conceded = compute_match_stats(_shot(keeper_y=20.0), run_id=None, name="t")
    assert saved.players[0].saves == 1
    assert conceded.players[0].saves == 0


def test_ac09_upload_endpoint(trace: dict[str, Any], stats: MatchStats) -> None:
    with TestClient(app) as client:
        ok = client.post("/stats", json=trace)
        empty = client.post("/stats", json={})
        no_players = client.post("/stats", json={"frames": [{"t": 0, "players": []}]})
    assert ok.status_code == 200
    assert ok.json() == stats.model_copy(update={"name": "upload"}).model_dump()
    assert empty.status_code == 422
    assert no_players.status_code == 422


@pytest.fixture(scope="module")
def run_id(trace: dict[str, Any]) -> int:
    try:
        conn = db.connect()
    except Exception:
        pytest.skip("PostgreSQL not reachable")
    with conn:
        seeded = db.seed_run(
            conn,
            name="test-match-stats",
            seed=7,
            meta=trace["meta"],
            slots=trace["slots"],
            frames=trace["frames"],
        )
    conn.close()
    return seeded


def test_ac09_run_stats_match_upload(run_id: int, stats: MatchStats) -> None:
    with TestClient(app) as client:
        got = client.get(f"/runs/{run_id}/stats")
        missing = client.get("/runs/999999/stats")
    assert got.status_code == 200
    expected = stats.model_copy(update={"run_id": run_id, "name": "test-match-stats"})
    assert got.json() == expected.model_dump()
    assert missing.status_code == 404


def test_ac09_run_stats_endpoint_without_postgres(
    monkeypatch: pytest.MonkeyPatch, trace: dict[str, Any], stats: MatchStats
) -> None:
    detail = {
        "id": 7,
        "name": "demo-65s",
        "meta": trace["meta"],
        "slots": trace["slots"],
        "frame_count": len(trace["frames"]),
    }
    monkeypatch.setattr(db, "connect", contextlib.nullcontext)
    monkeypatch.setattr(db, "get_run", lambda _c, rid: detail if rid == 7 else None)
    monkeypatch.setattr(
        db, "get_frames", lambda _c, _rid, *, from_idx, limit: trace["frames"][:limit]
    )
    with TestClient(app) as client:
        got = client.get("/runs/7/stats")
        missing = client.get("/runs/8/stats")
    assert (
        got.json()
        == stats.model_copy(update={"run_id": 7, "name": "demo-65s"}).model_dump()
    )
    assert missing.status_code == 404


def test_run_stats_503_when_database_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> None:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(db, "connect", refuse)
    with TestClient(app) as client:
        stats = client.get("/runs/1/stats")
        runs = client.get("/runs", headers={"Origin": "http://127.0.0.1:5500"})
    assert stats.status_code == 503
    # The page falls back to the JSON file only if it can read this answer.
    assert runs.status_code == 503
    assert runs.headers["access-control-allow-origin"] == "*"
