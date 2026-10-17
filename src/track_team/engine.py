"""Deterministic movement engine. No I/O: stepping is pure simulation (INV-4)."""

import math
from dataclasses import dataclass, field

from track_team.formations import SLOTS, Slot, scattered_positions
from track_team.metrics import compute_metrics
from track_team.models import FIELD_LENGTH_M, FIELD_WIDTH_M, Frame, Phase, PlayerState
from track_team.scenarios import ball_position, target_for

_MAX_ACCEL = 6.0  # m/s^2
_SEPARATION_M = 0.9
_DEMO_SCATTERED_S = 3.0
_DEMO_PHASE_S = 18.0


@dataclass
class _Player:
    slot: Slot
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    distance_m: float = 0.0


@dataclass
class Simulation:
    """Eleven players moving through scattered -> forming -> attack/defense."""

    seed: int = 7
    t: float = 0.0
    phase: Phase = Phase.IDLE
    running: bool = False
    auto_demo: bool = False
    _phase_t: float = 0.0
    _players: list[_Player] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reset(self.seed)

    def reset(self, seed: int = 7) -> None:
        """Return every player to a wrong, scattered starting position."""
        self.seed = seed
        self.t = 0.0
        self._phase_t = 0.0
        self.phase = Phase.SCATTERED
        self.running = False
        self.auto_demo = False
        start = scattered_positions(seed)
        self._players = [
            _Player(slot=slot, x=start[slot.id][0], y=start[slot.id][1])
            for slot in SLOTS
        ]

    def start(self) -> None:
        """Start moving from the scattered positions towards the formation."""
        self.phase = Phase.FORMING
        self._phase_t = 0.0
        self.running = True

    def set_phase(self, phase: Phase) -> None:
        """Switch scenario; players chase the new targets, never teleport."""
        self.phase = phase
        self._phase_t = 0.0
        self.running = True

    def run_demo(self) -> None:
        """Start the hands-free stage sequence (scattered -> form -> attack...)."""
        self.reset(self.seed)
        self.auto_demo = True
        self.running = True

    def step(self, dt: float = 0.1) -> Frame:
        """Advance the simulation by ``dt`` seconds and return the new frame."""
        if self.running and self.phase is not Phase.IDLE:
            self.t += dt
            self._phase_t += dt
            self._advance_demo_clock()
            # Scattered/idle players hold their (wrong) positions: no target yet.
            if self.phase in (Phase.FORMING, Phase.ATTACK, Phase.DEFENSE):
                ball = ball_position(self.phase, self.t)
                for index, player in enumerate(self._players):
                    target = target_for(player.slot, self.phase, self.t, ball, index)
                    self._move(player, target.x, target.y, dt)
                self._separate()
        return self.frame()

    def frame(self) -> Frame:
        """Return the current snapshot without advancing time."""
        players = [
            PlayerState(
                id=p.slot.id,
                role=p.slot.role,
                group=p.slot.group,
                x=round(p.x, 3),
                y=round(p.y, 3),
                vx=round(p.vx, 3),
                vy=round(p.vy, 3),
                speed=round(math.hypot(p.vx, p.vy), 3),
                distance_m=round(p.distance_m, 2),
            )
            for p in self._players
        ]
        return Frame(
            t=round(self.t, 3),
            phase=self.phase,
            ball=ball_position(self.phase, self.t),
            players=players,
            metrics=compute_metrics(players),
        )

    def _advance_demo_clock(self) -> None:
        if not self.auto_demo:
            return
        if self.phase is Phase.SCATTERED and self._phase_t >= _DEMO_SCATTERED_S:
            self.phase, self._phase_t = Phase.FORMING, 0.0
        elif (
            self.phase is Phase.FORMING and self.frame().metrics.formation_error_m < 1.0
        ):
            self.phase, self._phase_t = Phase.ATTACK, 0.0
        elif self.phase is Phase.ATTACK and self._phase_t >= _DEMO_PHASE_S:
            self.phase, self._phase_t = Phase.DEFENSE, 0.0
        elif self.phase is Phase.DEFENSE and self._phase_t >= _DEMO_PHASE_S:
            self.phase, self._phase_t = Phase.ATTACK, 0.0

    def _move(
        self, player: _Player, target_x: float, target_y: float, dt: float
    ) -> None:
        dx, dy = target_x - player.x, target_y - player.y
        dist = math.hypot(dx, dy)
        desired_speed = min(player.slot.v_max, dist * 1.2)  # slow down on arrival
        desired_vx = dx / dist * desired_speed if dist > 1e-9 else 0.0
        desired_vy = dy / dist * desired_speed if dist > 1e-9 else 0.0
        max_dv = _MAX_ACCEL * dt
        player.vx += max(-max_dv, min(max_dv, desired_vx - player.vx))
        player.vy += max(-max_dv, min(max_dv, desired_vy - player.vy))
        step_x, step_y = player.vx * dt, player.vy * dt
        player.x = min(FIELD_LENGTH_M, max(0.0, player.x + step_x))
        player.y = min(FIELD_WIDTH_M, max(0.0, player.y + step_y))
        player.distance_m += math.hypot(step_x, step_y)

    def _separate(self) -> None:
        for i, a in enumerate(self._players):
            for b in self._players[i + 1 :]:
                dx, dy = b.x - a.x, b.y - a.y
                dist = math.hypot(dx, dy)
                if 1e-9 < dist < _SEPARATION_M:
                    push = (_SEPARATION_M - dist) / 2.0
                    ux, uy = dx / dist, dy / dist
                    a.x -= ux * push
                    a.y -= uy * push
                    b.x += ux * push
                    b.y += uy * push
                    a.x = min(FIELD_LENGTH_M, max(0.0, a.x))
                    a.y = min(FIELD_WIDTH_M, max(0.0, a.y))
                    b.x = min(FIELD_LENGTH_M, max(0.0, b.x))
                    b.y = min(FIELD_WIDTH_M, max(0.0, b.y))
