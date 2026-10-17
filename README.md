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

### Replay from PostgreSQL (no full-JSON download)

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

Spec: `docs/specs/player-match-stats.md`. With the backend running as above,
open `http://127.0.0.1:5500/stats.html`: per-player distance, average/max
speed, passes, goals and saves for each run (`GET /runs/{id}/stats`), or for
a JSON file uploaded from the page (`POST /stats`).

Without Docker/PostgreSQL only the backend and the static server are needed:
the page falls back to `examples/simulation_trace.json` (or `?data=file.json`)
and computes its stats via `POST /stats`.

```bash
uv run uvicorn track_team.app:app --app-dir src --port 8765
python3 -m http.server 5500   # open http://127.0.0.1:5500/stats.html
```

## Authors
- Giorgio https://github.com/giorgiodare
- Imanol https://github.com/ImaKaiber25
- Loris https://github.com/lorisugolini
- Roberto https://github.com/RobertoDorata