"""Shared data contract: frames consumed by frontend and sensor branches."""

from enum import Enum

from pydantic import BaseModel

FIELD_LENGTH_M = 105.0
FIELD_WIDTH_M = 68.0
SENSOR_CORNERS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (FIELD_LENGTH_M, 0.0),
    (0.0, FIELD_WIDTH_M),
    (FIELD_LENGTH_M, FIELD_WIDTH_M),
)


class Phase(str, Enum):
    """Simulation phase."""

    IDLE = "idle"
    SCATTERED = "scattered"
    FORMING = "forming"
    ATTACK = "attack"
    DEFENSE = "defense"


class Vec2(BaseModel):
    """A point or vector on the pitch, in metres."""

    x: float
    y: float


class PlayerState(BaseModel):
    """Ground-truth state of one player in a frame."""

    id: str
    role: str
    group: str
    x: float
    y: float
    vx: float
    vy: float
    speed: float
    distance_m: float


class Metrics(BaseModel):
    """Team-level metrics for one frame."""

    formation_error_m: float
    centroid: Vec2
    team_length_m: float
    team_width_m: float
    line_gap_def_mid_m: float
    line_gap_mid_att_m: float


class Frame(BaseModel):
    """One simulation snapshot, broadcast at ~10 Hz."""

    t: float
    phase: Phase
    ball: Vec2
    players: list[PlayerState]
    metrics: Metrics


class PlayerMatchStats(BaseModel):
    """Per-player statistics over one match (docs/specs/player-match-stats.md)."""

    id: str
    role: str
    group: str
    distance_m: float
    avg_speed_mps: float
    max_speed_mps: float
    passes: int
    passes_received: int
    goals: int
    saves: int | None


class TeamMatchStats(BaseModel):
    """Team totals over one match; goals include unattributed ones."""

    distance_m: float
    passes: int
    goals: int


class MatchStats(BaseModel):
    """Statistics of one match: a recorded run or an uploaded trace."""

    run_id: int | None
    name: str
    duration_s: float
    frames: int
    players: list[PlayerMatchStats]
    team: TeamMatchStats
