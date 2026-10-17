# track-team
Hacktoberfest 2026

## Backend: player movement simulation

Spec: `docs/specs/player-simulation.md`. Contract example for the frontend
and sensor branches: `examples/frame.json` (WebSocket frames on `/ws/positions`).

```bash
uv sync
uv run uvicorn track_team.app:app --app-dir src --port 8000
curl -X POST http://127.0.0.1:8000/simulation/run-demo
uv run python scripts/demo_probe.py   # live formation error / centroid
```

## Replay from PostgreSQL (no full-JSON download)

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
