"""Team metrics derived from one frame's player positions."""

import math

from track_team.formations import SLOTS
from track_team.models import Metrics, PlayerState, Vec2


def compute_metrics(players: list[PlayerState]) -> Metrics:
    """Compute formation error, centroid, size and line gaps.

    Args:
        players: Player states of the frame being built.

    Returns:
        Aggregated metrics; formation error excludes the goalkeeper.
    """
    slots = {slot.id: slot for slot in SLOTS}
    outfield = [p for p in players if p.group != "GK"]
    error = sum(
        math.hypot(p.x - slots[p.id].x, p.y - slots[p.id].y) for p in outfield
    ) / max(1, len(outfield))
    xs = [p.x for p in players]
    ys = [p.y for p in players]

    def mean_x(group: str) -> float:
        values = [p.x for p in players if p.group == group]
        return sum(values) / len(values) if values else 0.0

    mid_x = mean_x("MID")
    return Metrics(
        formation_error_m=round(error, 3),
        centroid=Vec2(x=round(sum(xs) / len(xs), 3), y=round(sum(ys) / len(ys), 3)),
        team_length_m=round(max(xs) - min(xs), 3),
        team_width_m=round(max(ys) - min(ys), 3),
        line_gap_def_mid_m=round(mid_x - mean_x("DEF"), 3),
        line_gap_mid_att_m=round(mean_x("ATT") - mid_x, 3),
    )
