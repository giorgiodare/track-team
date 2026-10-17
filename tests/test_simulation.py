"""Acceptance checks for docs/specs/player-simulation.md (AC-01..AC-08)."""

import json
import math
from pathlib import Path

from fastapi.testclient import TestClient

from track_team.app import app
from track_team.engine import Simulation
from track_team.export import write_trace
from track_team.models import Frame, Phase


def _run(sim: Simulation, seconds: float) -> Frame:
    frame = sim.frame()
    for _ in range(int(seconds / 0.1)):
        frame = sim.step(0.1)
    return frame


def test_ac01_scattered_start_has_high_formation_error() -> None:
    sim = Simulation(seed=7)
    assert sim.frame().metrics.formation_error_m >= 5.0


def test_scattered_players_hold_wrong_positions() -> None:
    sim = Simulation(seed=7)
    sim.run_demo()
    before = [(p.x, p.y) for p in sim.frame().players]
    frame = _run(sim, 2.0)
    assert frame.phase is Phase.SCATTERED
    assert [(p.x, p.y) for p in frame.players] == before


def test_ac02_forming_converges_below_one_metre() -> None:
    sim = Simulation(seed=7)
    sim.start()
    frame = _run(sim, 20.0)
    assert frame.metrics.formation_error_m < 1.0


def test_ac03_attack_advances_centroid() -> None:
    sim = Simulation(seed=7)
    sim.start()
    forming = _run(sim, 20.0)
    sim.set_phase(Phase.ATTACK)
    attack = _run(sim, 20.0)
    assert attack.metrics.centroid.x > forming.metrics.centroid.x + 10.0


def test_ac04_defense_drops_and_compacts() -> None:
    sim = Simulation(seed=7)
    sim.start()
    _run(sim, 20.0)
    sim.set_phase(Phase.ATTACK)
    attack = _run(sim, 20.0)
    sim.set_phase(Phase.DEFENSE)
    defense = _run(sim, 20.0)
    assert defense.metrics.centroid.x < attack.metrics.centroid.x
    assert defense.metrics.team_length_m < attack.metrics.team_length_m


def test_ac05_bounds_and_speed_limits_hold() -> None:
    sim = Simulation(seed=7)
    sim.run_demo()
    v_max = {"GK": 5.0, "DEF": 7.5, "MID": 8.0, "ATT": 9.0}
    for _ in range(600):
        frame = sim.step(0.1)
        for player in frame.players:
            assert 0.0 <= player.x <= 105.0
            assert 0.0 <= player.y <= 68.0
            assert player.speed <= v_max[player.group] + 1e-6


def test_ac06_same_seed_same_trajectory() -> None:
    first, second = Simulation(seed=7), Simulation(seed=7)
    first.start()
    second.start()
    for _ in range(50):
        assert first.step(0.1) == second.step(0.1)


def test_ac07_api_health_state_and_websocket_first_frame() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        client.post("/simulation/reset", params={"seed": 7})
        state = client.get("/simulation/state").json()
        assert len(state["players"]) == 11
        with client.websocket_connect("/ws/positions") as websocket:
            frame = websocket.receive_json()
    assert frame["phase"] == "scattered"
    assert len(frame["players"]) == 11


def test_ac09_export_trace_json_covers_all_phases(tmp_path: Path) -> None:
    path = write_trace(tmp_path / "trace.json", seconds=65.0)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["formation"] == "4-4-2 diamond"
    assert len(payload["slots"]) == 11
    assert {frame["phase"] for frame in payload["frames"]} >= {
        "scattered",
        "forming",
        "attack",
        "defense",
    }
    assert all(len(frame["players"]) == 11 for frame in payload["frames"])


def test_ac10_attack_ball_stays_with_players_and_travels() -> None:
    sim = Simulation(seed=7)
    sim.start()
    _run(sim, 20.0)
    sim.set_phase(Phase.ATTACK)
    frames = [sim.step(0.1) for _ in range(120)]
    close = sum(
        min(math.hypot(f.ball.x - p.x, f.ball.y - p.y) for p in f.players) < 2.5
        for f in frames
    )
    travelled = sum(
        math.hypot(b.ball.x - a.ball.x, b.ball.y - a.ball.y)
        for a, b in zip(frames, frames[1:], strict=False)
    )
    assert close / len(frames) >= 0.5
    assert travelled > 30.0
    assert all(0.0 <= f.ball.x <= 105.0 and 0.0 <= f.ball.y <= 68.0 for f in frames)


def test_ac11_defense_ball_stays_in_front_of_block() -> None:
    sim = Simulation(seed=7)
    sim.start()
    _run(sim, 20.0)
    sim.set_phase(Phase.DEFENSE)
    frames = [sim.step(0.1) for _ in range(120)]
    assert all(f.ball.x >= 55.0 for f in frames)
    assert all(0.0 <= f.ball.y <= 68.0 for f in frames)


def test_ac12_video_pattern_alternates_flanks_and_finishes() -> None:
    sim = Simulation(seed=7)
    sim.start()
    _run(sim, 20.0)
    sim.set_phase(Phase.ATTACK)
    frames = [sim.step(0.1) for _ in range(320)]
    max_x = {
        pid: max(p.x for f in frames for p in f.players if p.id == pid)
        for pid in ("P2", "P5", "P10", "P11")
    }
    assert max_x["P5"] > 85.0  # right full-back overlaps on cycle 1
    assert max_x["P2"] > 85.0  # left full-back overlaps on cycle 2
    assert max(max_x["P10"], max_x["P11"]) > 90.0  # striker attacks the box
    assert max(f.ball.x for f in frames) > 100.0  # shot on goal


def test_ac08_frame_contract_round_trips() -> None:
    sim = Simulation(seed=7)
    frame = sim.frame()
    assert Frame.model_validate(frame.model_dump(mode="json")) == frame
