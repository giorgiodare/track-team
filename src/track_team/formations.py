"""4-4-2 diamond formation slots and the deliberately wrong start positions."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    """Ideal position of one player in the 4-4-2 diamond."""

    id: str
    role: str
    group: str  # GK | DEF | MID | ATT
    x: float
    y: float
    v_max: float  # m/s


# x: 0 = own goal line, 105 = opponent goal line. y: 0..68 across the pitch.
SLOTS: tuple[Slot, ...] = (
    Slot("P1", "GK", "GK", 5.0, 34.0, 5.0),
    Slot("P2", "LB", "DEF", 22.0, 12.0, 7.5),
    Slot("P3", "LCB", "DEF", 18.0, 27.0, 7.5),
    Slot("P4", "RCB", "DEF", 18.0, 41.0, 7.5),
    Slot("P5", "RB", "DEF", 22.0, 56.0, 7.5),
    Slot("P6", "DM", "MID", 35.0, 34.0, 8.0),
    Slot("P7", "LCM", "MID", 48.0, 20.0, 8.0),
    Slot("P8", "RCM", "MID", 48.0, 48.0, 8.0),
    Slot("P9", "AM", "MID", 58.0, 34.0, 8.0),
    Slot("P10", "LS", "ATT", 72.0, 26.0, 9.0),
    Slot("P11", "RS", "ATT", 72.0, 42.0, 9.0),
)


def scattered_positions(seed: int) -> dict[str, tuple[float, float]]:
    """Wrong starting positions: slot plus large deterministic jitter (AC-01)."""
    rng = random.Random(seed)
    positions: dict[str, tuple[float, float]] = {}
    for slot in SLOTS:
        x = min(100.0, max(3.0, slot.x + rng.uniform(-20.0, 20.0)))
        y = min(65.0, max(3.0, slot.y + rng.uniform(-16.0, 16.0)))
        positions[slot.id] = (x, y)
    return positions
