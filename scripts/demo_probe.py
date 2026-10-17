"""Stage check: start run-demo and print formation error / centroid live.

Usage: uv run python scripts/demo_probe.py [seconds]
"""

import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("TRACK_TEAM_URL", "http://127.0.0.1:8000")


def _request(path: str, *, method: str = "GET") -> dict:
    request = urllib.request.Request(f"{BASE}{path}", method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def main() -> None:
    """Run the demo sequence and print the headline metrics once a second."""
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    _request("/simulation/run-demo", method="POST")
    for _ in range(seconds):
        time.sleep(1.0)
        frame = _request("/simulation/state")
        metrics = frame["metrics"]
        print(
            f"t={frame['t']:6.1f}s phase={frame['phase']:9s} "
            f"formation_error={metrics['formation_error_m']:5.2f} m "
            f"centroid_x={metrics['centroid']['x']:5.1f} "
            f"team_length={metrics['team_length_m']:5.1f} m",
            flush=True,
        )


if __name__ == "__main__":
    main()
