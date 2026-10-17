"""Per-player match statistics derived from a recorded trace (no I/O).

Passes, goals and saves are not stored as events: they are inferred from
ball and player positions frame by frame (docs/specs/player-match-stats.md §4).
"""

import math
from typing import Any

from track_team.models import (
    FIELD_LENGTH_M,
    FIELD_WIDTH_M,
    MatchStats,
    PlayerMatchStats,
    TeamMatchStats,
)

POSSESSION_RADIUS_M = 1.5
POSSESSION_DEBOUNCE_FRAMES = 3
GOAL_LINE_X_M = 103.5
GOAL_HALF_WIDTH_M = 3.66
SHOT_MIN_SPEED_MPS = 12.0

_GOAL_Y_M = FIELD_WIDTH_M / 2
_OWN_GOAL_LINE_X_M = FIELD_LENGTH_M - GOAL_LINE_X_M


def _player_order(player_id: str) -> tuple[int, str]:
    """Sort P1, P2, ..., P11 numerically; unknown ids go last, by name."""
    digits = player_id[1:]
    return (int(digits), "") if digits.isdigit() else (10**9, player_id)


def _between_posts(y: float) -> bool:
    return abs(y - _GOAL_Y_M) <= GOAL_HALF_WIDTH_M


def _nearest_within(
    ball: dict[str, float], players: list[dict[str, Any]], radius: float
) -> dict[str, Any] | None:
    """Return the player closest to the ball if within ``radius``, else None."""
    best: dict[str, Any] | None = None
    best_d = radius
    for p in players:
        d = math.hypot(p["x"] - ball["x"], p["y"] - ball["y"])
        if d <= best_d:
            best, best_d = p, d
    return best


def _validated_frames(trace: dict[str, Any]) -> list[dict[str, Any]]:
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("trace has no frames")
    if any(not isinstance(f, dict) or not f.get("players") for f in frames):
        raise ValueError("every frame needs a non-empty players list")
    return sorted(frames, key=lambda f: f["t"])


def compute_match_stats(
    trace: dict[str, Any], *, run_id: int | None, name: str
) -> MatchStats:
    """Compute distance, speed, passes, goals and saves for every player.

    Args:
        trace: Match in the export shape ``{meta, slots, frames}``.
        run_id: Database run id, or ``None`` for an uploaded trace.
        name: Run name, or ``"upload"``.

    Returns:
        Per-player and team statistics, rounded to 2 decimals.

    Raises:
        ValueError: If the trace has no frames or a frame has no players.
    """
    frames = _validated_frames(trace)
    duration = frames[-1]["t"] - frames[0]["t"]

    info: dict[str, dict[str, Any]] = {}
    first_dist: dict[str, float] = {}
    last_dist: dict[str, float] = {}
    path: dict[str, float] = {}
    last_pos: dict[str, tuple[float, float]] = {}
    max_speed: dict[str, float] = {}
    has_distance_field = True
    for f in frames:
        for p in f["players"]:
            pid = p["id"]
            info.setdefault(pid, {"role": p["role"], "group": p["group"]})
            if "distance_m" in p:
                first_dist.setdefault(pid, p["distance_m"])
                last_dist[pid] = p["distance_m"]
            else:
                has_distance_field = False
            if pid in last_pos:
                px, py = last_pos[pid]
                path[pid] = path.get(pid, 0.0) + math.hypot(p["x"] - px, p["y"] - py)
            last_pos[pid] = (p["x"], p["y"])
            max_speed[pid] = max(max_speed.get(pid, 0.0), p.get("speed", 0.0))

    passes = dict.fromkeys(info, 0)
    received = dict.fromkeys(info, 0)
    goals = dict.fromkeys(info, 0)
    saves = {pid: 0 for pid, i in info.items() if i["group"] == "GK"}
    team_goals = 0

    candidate: str | None = None
    run = 0
    holder: str | None = None
    in_goal = False
    shot_active = False
    prev: dict[str, Any] | None = None
    for f in frames:
        ball = f["ball"]
        phase = f["phase"]
        if prev is not None and prev["phase"] != phase:
            candidate, run, holder, shot_active = None, 0, None, False

        # §4.3–4.4 possession and passes, only while attacking.
        if phase == "attack":
            nearest = _nearest_within(ball, f["players"], POSSESSION_RADIUS_M)
            cand = nearest["id"] if nearest else None
            if cand is not None and cand == candidate:
                run += 1
            else:
                candidate, run = cand, 1 if cand else 0
            if candidate and run >= POSSESSION_DEBOUNCE_FRAMES and candidate != holder:
                if holder is not None:
                    passes[holder] += 1
                    received[candidate] += 1
                holder = candidate

        # §4.5 goals: counted once per entry, credited to the last holder.
        scored = ball["x"] >= GOAL_LINE_X_M and _between_posts(ball["y"])
        if scored and not in_goal:
            team_goals += 1
            if holder is not None:
                goals[holder] += 1
            candidate, run, holder = None, 0, None
        in_goal = scored

        # §4.6 saves: fast opponent ball towards x = 0 reaching our goalkeeper.
        if phase == "defense" and prev is not None and f["t"] > prev["t"]:
            step = f["t"] - prev["t"]
            dx = ball["x"] - prev["ball"]["x"]
            dy = ball["y"] - prev["ball"]["y"]
            fast_inbound = dx < 0 and math.hypot(dx, dy) / step >= SHOT_MIN_SPEED_MPS
            shot_active = shot_active or fast_inbound
            if shot_active:
                keepers = [p for p in f["players"] if p["group"] == "GK"]
                keeper = _nearest_within(ball, keepers, POSSESSION_RADIUS_M)
                if keeper is not None:
                    saves[keeper["id"]] = saves.get(keeper["id"], 0) + 1
                    shot_active = False
                elif ball["x"] <= _OWN_GOAL_LINE_X_M or not fast_inbound:
                    shot_active = False
        prev = f

    players = []
    for pid in sorted(info, key=_player_order):
        if has_distance_field and pid in last_dist:
            distance = last_dist[pid] - first_dist[pid]
        else:
            distance = path.get(pid, 0.0)
        players.append(
            PlayerMatchStats(
                id=pid,
                role=info[pid]["role"],
                group=info[pid]["group"],
                distance_m=round(distance, 2),
                avg_speed_mps=round(distance / duration, 2) if duration > 0 else 0.0,
                max_speed_mps=round(max_speed[pid], 2),
                passes=passes[pid],
                passes_received=received[pid],
                goals=goals[pid],
                saves=saves.get(pid) if info[pid]["group"] == "GK" else None,
            )
        )
    return MatchStats(
        run_id=run_id,
        name=name,
        duration_s=round(duration, 2),
        frames=len(frames),
        players=players,
        team=TeamMatchStats(
            distance_m=round(sum(p.distance_m for p in players), 2),
            passes=sum(passes.values()),
            goals=team_goals,
        ),
    )
