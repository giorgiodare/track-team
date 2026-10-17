"""Scripted per-phase targets: where each player should be, moment by moment."""

import math

from track_team.formations import Slot
from track_team.models import Phase, Vec2

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


def _attack_target(slot: Slot, t: float, index: int) -> Vec2:
    """Waypoint target of the video pattern: build -> wide -> cross -> recover.

    The 16 s cycle alternates flank: the overlapping full-back and the
    ball-side mezzala create the width, the two strikers attack near/far
    post. ``t`` is time since the attack phase started.
    """
    cycle = t % 16.0
    right = int(t // 16.0) % 2 == 0
    s = 1.0 if right else -1.0

    def flank_y(offset: float) -> float:
        return 34.0 + offset * s

    flank_fb = "P5" if right else "P2"
    other_fb = "P2" if right else "P5"
    wide_mid = "P8" if right else "P7"
    near_striker = "P11" if right else "P10"
    far_striker = "P10" if right else "P11"

    pos: dict[str, tuple[float, float]] = {
        "P1": (14.0, 34.0),
        "P2": (46.0, 14.0),
        "P3": (40.0, 27.0),
        "P4": (40.0, 41.0),
        "P5": (46.0, 54.0),
        "P6": (52.0, 34.0),
        "P7": (62.0, 21.0),
        "P8": (62.0, 47.0),
        "P9": (70.0, 34.0),
        "P10": (78.0, 26.0),
        "P11": (78.0, 42.0),
    }
    if 5.0 <= cycle < 9.0:  # switch wide: full-back overlaps, mezzala carries
        pos[flank_fb] = (82.0, flank_y(28.0))
        pos[other_fb] = (48.0, flank_y(-22.0))
        pos[wide_mid] = (76.0, flank_y(16.0))
        pos["P9"] = (74.0, flank_y(4.0))
        pos["P6"] = (58.0, 34.0)
        pos[near_striker] = (88.0, flank_y(10.0))
        pos[far_striker] = (86.0, flank_y(-8.0))
    elif 9.0 <= cycle < 12.0:  # cross and finish at near/far post
        pos[flank_fb] = (95.0, flank_y(29.0))
        pos[other_fb] = (52.0, flank_y(-22.0))
        pos[wide_mid] = (82.0, flank_y(18.0))
        pos["P9"] = (84.0, 34.0)
        pos["P6"] = (64.0, 34.0)
        pos[near_striker] = (96.0, flank_y(7.0))
        pos[far_striker] = (93.0, flank_y(-9.0))
    elif cycle >= 12.0:  # recover to the attacking shape, next cycle flips side
        pos = dict(ATTACK_POS)
    x, y = pos[slot.id]
    return Vec2(x=x, y=y + 0.8 * math.sin(t * 0.6 + index * 2.1))


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
        return _attack_target(slot, t, index)
    if phase is Phase.DEFENSE:
        base_x, base_y = DEFENSE_POS[slot.id]
        slide = max(-8.0, min(8.0, (ball.y - 34.0) * 0.25))
        if slot.id == "P10":  # nearest striker presses towards the ball, then holds
            return Vec2(x=base_x + (ball.x - 14.0 - base_x) * 0.35, y=base_y + slide)
        return Vec2(x=base_x, y=base_y + (slide * 0.5 if slot.group == "GK" else slide))
    return Vec2(x=slot.x, y=slot.y)
