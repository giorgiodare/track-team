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
