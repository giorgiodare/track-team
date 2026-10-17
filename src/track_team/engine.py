"""Deterministic movement engine. No I/O: stepping is pure simulation (INV-4)."""

import math
from dataclasses import dataclass, field

from track_team.formations import SLOTS, Slot, scattered_positions
from track_team.metrics import compute_metrics
from track_team.models import (
    FIELD_LENGTH_M,
    FIELD_WIDTH_M,
    Frame,
    Phase,
    PlayerState,
    Vec2,
)
from track_team.scenarios import target_for

_MAX_ACCEL = 6.0  # m/s^2
_SEPARATION_M = 0.9
_DEMO_SCATTERED_S = 3.0
_DEMO_PHASE_S = 18.0
_PASS_SPEED = 18.0  # m/s
_SHOT_SPEED = 25.0  # m/s
_GOAL: tuple[float, float] = (104.0, 34.0)
# Opponent ball waypoints in front of the defensive block.
_DEF_WAYPOINTS: tuple[tuple[float, float], ...] = (
    (72.0, 18.0),
    (84.0, 34.0),
    (72.0, 50.0),
    (62.0, 34.0),
)


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
    _ball_x: float = FIELD_LENGTH_M / 2.0
    _ball_y: float = FIELD_WIDTH_M / 2.0
    _sched_pos: int = 0
    _pass_player: str | None = None
    _pass_point: tuple[float, float] | None = None
    _def_wp: int = 0

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
        self._place_ball()

    def start(self) -> None:
        """Start moving from the scattered positions towards the formation."""
        self._enter_phase(Phase.FORMING)
        self.running = True

    def set_phase(self, phase: Phase) -> None:
        """Switch scenario; players chase the new targets, never teleport."""
        self._enter_phase(phase)
        self.running = True

    def _enter_phase(self, phase: Phase) -> None:
        self.phase = phase
        self._phase_t = 0.0
        self._place_ball()

    def _place_ball(self) -> None:
        """Put the ball where the new phase starts: carrier, waypoint, centre."""
        self._sched_pos = 0
        self._pass_player = None
        self._pass_point = None
        self._def_wp = 0
        if self.phase is Phase.ATTACK and self._players:
            carrier = self._by_id("P6")
            self._ball_x, self._ball_y = carrier.x + 0.8, carrier.y
        elif self.phase is Phase.DEFENSE:
            self._ball_x, self._ball_y = _DEF_WAYPOINTS[0]
        else:
            self._ball_x, self._ball_y = FIELD_LENGTH_M / 2.0, FIELD_WIDTH_M / 2.0

    def _by_id(self, player_id: str) -> _Player:
        return next(p for p in self._players if p.slot.id == player_id)

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
                ball = Vec2(x=self._ball_x, y=self._ball_y)
                for index, player in enumerate(self._players):
                    target = target_for(
                        player.slot, self.phase, self._phase_t, ball, index
                    )
                    self._move(player, target.x, target.y, dt)
                self._separate()
                self._update_ball(dt)
        return self.frame()

    def _update_ball(self, dt: float) -> None:
        """Move the ball with the players: dribble, pass, or opponent dribble."""
        if self.phase is Phase.ATTACK:
            self._update_attack_ball(dt)
        elif self.phase is Phase.DEFENSE:
            target_x, target_y = _DEF_WAYPOINTS[self._def_wp]
            if self._move_ball_towards(target_x, target_y, 6.0, dt):
                self._def_wp = (self._def_wp + 1) % len(_DEF_WAYPOINTS)

    def _attack_schedule(self) -> list[tuple[float, str | None]]:
        """Timed ball sequence of the pattern; ``None`` is the shot on goal."""
        right = int(self._phase_t // 16.0) % 2 == 0
        wide_mid = "P8" if right else "P7"
        flank_fb = "P5" if right else "P2"
        near_striker = "P11" if right else "P10"
        return [
            (0.0, "P6"),
            (2.0, wide_mid),
            (4.0, "P9"),
            (6.0, flank_fb),
            (9.5, near_striker),
            (11.0, None),
        ]

    def _update_attack_ball(self, dt: float) -> None:
        schedule = self._attack_schedule()
        within = self._phase_t % 16.0
        passing = self._pass_player is not None or self._pass_point is not None
        if within < 1.0 and self._sched_pos > 0 and not passing:
            self._sched_pos = 0  # new cycle: ball back to the DM
        desired = max(i for i, (start, _) in enumerate(schedule) if start <= within)
        if self._pass_player is not None:
            receiver = self._by_id(self._pass_player)
            if self._move_ball_towards(receiver.x, receiver.y, _PASS_SPEED, dt):
                self._pass_player = None
        elif self._pass_point is not None:
            if self._move_ball_towards(*self._pass_point, _SHOT_SPEED, dt):
                self._pass_point = None
        elif desired > self._sched_pos:
            self._sched_pos = desired
            target = schedule[desired][1]
            if target is None:
                self._pass_point = _GOAL
            else:
                self._pass_player = target
        else:
            carrier_id = schedule[self._sched_pos][1]
            if carrier_id is not None:  # after the shot the ball stays in goal
                carrier = self._by_id(carrier_id)
                self._ball_x = min(FIELD_LENGTH_M, carrier.x + 0.8)
                self._ball_y = carrier.y

    def _move_ball_towards(
        self, target_x: float, target_y: float, speed: float, dt: float
    ) -> bool:
        dx, dy = target_x - self._ball_x, target_y - self._ball_y
        dist = math.hypot(dx, dy)
        step = speed * dt
        if dist <= max(step, 0.5):
            self._ball_x, self._ball_y = target_x, target_y
            return True
        self._ball_x += dx / dist * step
        self._ball_y += dy / dist * step
        return False

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
            ball=Vec2(x=round(self._ball_x, 3), y=round(self._ball_y, 3)),
            players=players,
            metrics=compute_metrics(players),
        )

    def _advance_demo_clock(self) -> None:
        if not self.auto_demo:
            return
        if self.phase is Phase.SCATTERED and self._phase_t >= _DEMO_SCATTERED_S:
            self._enter_phase(Phase.FORMING)
        elif (
            self.phase is Phase.FORMING and self.frame().metrics.formation_error_m < 1.0
        ):
            self._enter_phase(Phase.ATTACK)
        elif self.phase is Phase.ATTACK and self._phase_t >= _DEMO_PHASE_S:
            self._enter_phase(Phase.DEFENSE)
        elif self.phase is Phase.DEFENSE and self._phase_t >= _DEMO_PHASE_S:
            self._enter_phase(Phase.ATTACK)

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
        speed = math.hypot(player.vx, player.vy)
        if speed > player.slot.v_max:  # steering must never break INV-2
            player.vx *= player.slot.v_max / speed
            player.vy *= player.slot.v_max / speed
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
