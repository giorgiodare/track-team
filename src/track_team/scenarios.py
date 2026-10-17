"""Scripted per-phase targets: where each player should be, moment by moment."""

import math

from track_team.formations import Slot
from track_team.models import FIELD_LENGTH_M, FIELD_WIDTH_M, Phase, Vec2

# Full attacking shape: RB overlaps high, AM between the lines, strikers in the box.
ATTACK_POS: dict[str, tuple[float, float]] = {
    "P1": (14.0, 34.0),
    "P2": (48.0, 10.0),
    "P3": (42.0, 26.0),
    "P4": (42.0, 42.0),
    "P5": (78.0, 58.0),
    "P6": (58.0, 34.0),
    "P7": (70.0, 18.0),
    "P8": (74.0, 48.0),
    "P9": (82.0, 34.0),
    "P10": (90.0, 24.0),
    "P11": (92.0, 44.0),
}

# Compact defensive block in front of the own box.
DEFENSE_POS: dict[str, tuple[float, float]] = {
    "P1": (5.0, 34.0),
    "P2": (20.0, 14.0),
    "P3": (16.0, 27.0),
    "P4": (16.0, 41.0),
    "P5": (20.0, 54.0),
    "P6": (28.0, 34.0),
    "P7": (34.0, 22.0),
    "P8": (34.0, 46.0),
    "P9": (40.0, 34.0),
    "P10": (46.0, 28.0),
    "P11": (46.0, 40.0),
}

# Looping run amplitudes (m) so attacking players keep moving, never statues.
_RUN_AMP: dict[str, tuple[float, float]] = {
    "P5": (5.0, 3.0),
    "P7": (6.0, 3.0),
    "P8": (6.0, 3.0),
    "P9": (5.0, 4.0),
    "P10": (4.0, 5.0),
    "P11": (4.0, 5.0),
}


def ball_position(phase: Phase, t: float) -> Vec2:
    """Return the scripted ball position for a phase at time ``t``."""
    if phase is Phase.ATTACK:
        progress = (t % 24.0) / 24.0
        return Vec2(
            x=45.0 + 50.0 * progress,
            y=34.0 + 18.0 * math.sin(progress * math.pi * 3.0),
        )
    if phase is Phase.DEFENSE:
        return Vec2(
            x=74.0 + 14.0 * math.sin(t * 0.30),
            y=34.0 + 22.0 * math.sin(t * 0.23 + 1.0),
        )
    return Vec2(x=FIELD_LENGTH_M / 2.0, y=FIELD_WIDTH_M / 2.0)


def target_for(slot: Slot, phase: Phase, t: float, ball: Vec2, index: int) -> Vec2:
    """Return the instantaneous movement target of one player.

    Args:
        slot: The player's formation slot (also the `forming` target).
        phase: Current simulation phase.
        t: Simulation time in seconds.
        ball: Current ball position (drives the defensive slide and press).
        index: Player index, used to de-synchronise the looping runs.

    Returns:
        Target point in metres, always inside the pitch.
    """
    if phase is Phase.ATTACK:
        base_x, base_y = ATTACK_POS[slot.id]
        amp_x, amp_y = _RUN_AMP.get(slot.id, (1.5, 1.5))
        return Vec2(
            x=base_x + amp_x * math.sin(t * 0.45 + index * 1.3),
            y=base_y + amp_y * math.sin(t * 0.60 + index * 2.1),
        )
    if phase is Phase.DEFENSE:
        base_x, base_y = DEFENSE_POS[slot.id]
        slide = max(-8.0, min(8.0, (ball.y - 34.0) * 0.25))
        if slot.id == "P10":  # nearest striker presses towards the ball, then holds
            return Vec2(x=base_x + (ball.x - 14.0 - base_x) * 0.35, y=base_y + slide)
        return Vec2(x=base_x, y=base_y + (slide * 0.5 if slot.group == "GK" else slide))
    return Vec2(x=slot.x, y=slot.y)
