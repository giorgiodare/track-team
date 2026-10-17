"""PostgreSQL storage for recorded runs: schema, seeding, chunk reads."""

import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DEFAULT_DATABASE_URL = "postgresql://trackteam:trackteam@127.0.0.1:5434/trackteam"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    seed INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta JSONB NOT NULL,
    slots JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS frames (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    t DOUBLE PRECISION NOT NULL,
    phase TEXT NOT NULL,
    ball_x DOUBLE PRECISION NOT NULL,
    ball_y DOUBLE PRECISION NOT NULL,
    metrics JSONB NOT NULL,
    PRIMARY KEY (run_id, idx)
);
CREATE TABLE IF NOT EXISTS player_positions (
    run_id INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    role TEXT NOT NULL,
    "group" TEXT NOT NULL,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    vx DOUBLE PRECISION NOT NULL,
    vy DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION NOT NULL,
    distance_m DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (run_id, frame_idx, player_id),
    FOREIGN KEY (run_id, frame_idx) REFERENCES frames(run_id, idx) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS positions_player_idx
    ON player_positions (run_id, player_id, frame_idx);
"""


def connect() -> psycopg.Connection[dict[str, Any]]:
    """Open a connection using ``DATABASE_URL`` (local compose default)."""
    return psycopg.connect(
        os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL), row_factory=dict_row
    )


def init_schema(conn: psycopg.Connection[dict[str, Any]]) -> None:
    """Create tables and indexes if they do not exist yet."""
    conn.execute(_SCHEMA)
    conn.commit()


def seed_run(
    conn: psycopg.Connection[dict[str, Any]],
    *,
    name: str,
    seed: int,
    meta: dict[str, Any],
    slots: list[dict[str, Any]],
    frames: list[dict[str, Any]],
) -> int:
    """Insert one run with all frames/positions, replacing a same-named run.

    Args:
        conn: Open connection; the whole insert is one transaction.
        name: Run name; an existing run with this name is deleted first.
        seed: Simulation seed that produced the frames.
        meta: Run metadata stored as JSONB.
        slots: Formation slots stored as JSONB.
        frames: Frame dicts in the export-JSON shape.

    Returns:
        The new run id.
    """
    init_schema(conn)
    with conn.transaction():
        conn.execute("DELETE FROM runs WHERE name = %s", (name,))
        row = conn.execute(
            "INSERT INTO runs (name, seed, meta, slots) VALUES (%s, %s, %s, %s)"
            " RETURNING id",
            (name, seed, Jsonb(meta), Jsonb(slots)),
        ).fetchone()
        run_id = int(row["id"]) if row else 0
        with conn.cursor().copy(
            "COPY frames (run_id, idx, t, phase, ball_x, ball_y, metrics) FROM STDIN"
        ) as copy:
            for idx, frame in enumerate(frames):
                copy.write_row(
                    (
                        run_id,
                        idx,
                        frame["t"],
                        frame["phase"],
                        frame["ball"]["x"],
                        frame["ball"]["y"],
                        json.dumps(frame["metrics"]),
                    )
                )
        with conn.cursor().copy(
            "COPY player_positions (run_id, frame_idx, player_id, role,"
            ' "group", x, y, vx, vy, speed, distance_m) FROM STDIN'
        ) as copy:
            for idx, frame in enumerate(frames):
                for p in frame["players"]:
                    copy.write_row(
                        (
                            run_id,
                            idx,
                            p["id"],
                            p["role"],
                            p["group"],
                            p["x"],
                            p["y"],
                            p["vx"],
                            p["vy"],
                            p["speed"],
                            p["distance_m"],
                        )
                    )
    return run_id


def list_runs(conn: psycopg.Connection[dict[str, Any]]) -> list[dict[str, Any]]:
    """List recorded runs with frame counts, newest first."""
    init_schema(conn)
    return conn.execute(
        "SELECT r.id, r.name, r.seed, r.created_at,"
        " (SELECT count(*) FROM frames f WHERE f.run_id = r.id) AS frame_count,"
        " (SELECT max(t) FROM frames f WHERE f.run_id = r.id) AS duration_s"
        " FROM runs r ORDER BY r.id DESC"
    ).fetchall()


def get_run(
    conn: psycopg.Connection[dict[str, Any]], run_id: int
) -> dict[str, Any] | None:
    """Return one run's metadata, slots and frame count, or ``None``."""
    row = conn.execute(
        "SELECT r.id, r.name, r.seed, r.meta, r.slots,"
        " (SELECT count(*) FROM frames f WHERE f.run_id = r.id) AS frame_count,"
        " (SELECT max(t) FROM frames f WHERE f.run_id = r.id) AS duration_s"
        " FROM runs r WHERE r.id = %s",
        (run_id,),
    ).fetchone()
    return row


def get_frames(
    conn: psycopg.Connection[dict[str, Any]],
    run_id: int,
    *,
    from_idx: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Return a chunk of frames in the export-JSON shape, ordered by idx."""
    frame_rows = conn.execute(
        "SELECT idx, t, phase, ball_x, ball_y, metrics FROM frames"
        " WHERE run_id = %s AND idx >= %s ORDER BY idx LIMIT %s",
        (run_id, from_idx, limit),
    ).fetchall()
    if not frame_rows:
        return []
    last_idx = int(frame_rows[-1]["idx"])
    pos_rows = conn.execute(
        'SELECT frame_idx, player_id, role, "group", x, y, vx, vy, speed, distance_m'
        " FROM player_positions WHERE run_id = %s AND frame_idx BETWEEN %s AND %s"
        " ORDER BY frame_idx, player_id",
        (run_id, from_idx, last_idx),
    ).fetchall()
    players_by_idx: dict[int, list[dict[str, Any]]] = {}
    for pos in pos_rows:
        players_by_idx.setdefault(int(pos["frame_idx"]), []).append(
            {
                "id": pos["player_id"],
                "role": pos["role"],
                "group": pos["group"],
                "x": pos["x"],
                "y": pos["y"],
                "vx": pos["vx"],
                "vy": pos["vy"],
                "speed": pos["speed"],
                "distance_m": pos["distance_m"],
            }
        )
    # Player ids sort as P1, P10, P11, P2... restore numeric order.
    for players in players_by_idx.values():
        players.sort(key=lambda p: int(str(p["id"])[1:]))
    return [
        {
            "t": row["t"],
            "phase": row["phase"],
            "ball": {"x": row["ball_x"], "y": row["ball_y"]},
            "players": players_by_idx.get(int(row["idx"]), []),
            "metrics": row["metrics"],
        }
        for row in frame_rows
    ]
