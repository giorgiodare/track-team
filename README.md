# track-team
Hacktoberfest 2026

## Problem
Help small sports team to gather data from practices to improve team play and generate predictive metrics.

## Solution
Using tracking tags for each player and a minimun of 4 receivers for field area, we can collect data from the players position during the games and training matches.

## Stack
- Backend Python, FastAPI
- Frontend HTML, CSS, JS

## Instructions

### Backend: player movement simulation

Spec: `docs/specs/player-simulation.md`. Contract example for the frontend
and sensor branches: `examples/frame.json` (WebSocket frames on `/ws/positions`).

```bash
uv sync
uv run uvicorn track_team.app:app --app-dir src --port 8000
curl -X POST http://127.0.0.1:8000/simulation/run-demo
uv run python scripts/demo_probe.py   # live formation error / centroid
```

### Replay from PostgreSQL

```bash
docker compose up -d                       # PostgreSQL on 127.0.0.1:5434
uv run python scripts/seed_db.py           # inserts run "demo-65s" (650 frames)
uv run uvicorn track_team.app:app --app-dir src --port 8765
python3 -m http.server 5500                # serves index.html
# open http://127.0.0.1:5500/index.html?fps=1
```

The page reads frames from `GET /runs/{id}/frames` in chunks of 100
(10 s at 10 fps) with prefetch; `?data=file.json` keeps the old
whole-file fallback.

### Match stats page

Spec: `docs/specs/player-match-stats.md`. One match = one export JSON
(`{meta, slots, frames}`), stored in PostgreSQL as a run or read as a file.
`stats.html` shows, per player: distance, average and max speed, passes made
and received, goals, and saves (goalkeeper only), plus team totals.

## Run it

With PostgreSQL, start everything as in the replay section above, then open
`http://127.0.0.1:5500/stats.html`.

Without Docker/PostgreSQL only the backend and the static server are needed:

```bash
uv run uvicorn track_team.app:app --app-dir src --port 8765
python3 -m http.server 5500   # open http://127.0.0.1:5500/stats.html
```

When `GET /runs` fails or returns no runs, the page loads
`examples/simulation_trace.json` and sends it to `POST /stats`. Stats are
always computed by the backend, which starts fine without a database.

URL parameters: `?api=` backend URL (default `http://127.0.0.1:8765`),
`?run=<id>` preselects a run, `?data=file.json` uses that file and skips
the database. "Carica JSON" uploads any export file; "Apri replay" opens
the same match in `index.html`.

### How the metrics are computed

The JSON has no events, so passes, goals and saves are inferred from
positions frame by frame (`src/track_team/match_stats.py`, no I/O):

| Metric | Rule |
|---|---|
| Distance | last minus first `distance_m` of the player |
| Avg speed | distance / match duration (shown in km/h) |
| Possession | nearest player within 1.5 m of the ball for 3 consecutive frames, `attack` phase only |
| Pass | possession moves from A to B; a goal or a phase change resets the chain |
| Goal | ball enters the opponent goal (`x ≥ 103.5`, between the posts), credited to the last holder |
| Save | in `defense`, a ball heading to `x = 0` at ≥ 12 m/s reaches the goalkeeper |

On `examples/simulation_trace.json` this gives 8 passes, 2 goals by P11 and
0 saves (the simulator has no opponent shots yet).

### API

| Method | Path | Result |
|---|---|---|
| GET | `/runs/{id}/stats` | stats of a stored run (404 if missing) |
| POST | `/stats` | stats of an uploaded export JSON (422 if invalid) |

When PostgreSQL is down every `/runs…` endpoint answers `503 database not
reachable` with CORS headers, so browser pages can tell it apart from a
backend that is not running.

### Tests

```bash
uv run pytest      # stats acceptance checks: tests/test_match_stats.py
```

Tests that need PostgreSQL are skipped when it is not reachable. The page
itself (AC-10/AC-11) is checked by hand in the browser.

## Authors
- Giorgio https://github.com/giorgiodare
- Imanol https://github.com/ImaKaiber25
- Loris https://github.com/lorisugolini
- Roberto https://github.com/RobertoDorata
