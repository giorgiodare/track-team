"""Write the demo simulation trace to JSON.

Usage: uv run python scripts/export_trace.py [path] [seconds]
"""

import sys
from pathlib import Path

from track_team.export import write_trace


def main() -> None:
    """Generate the trace JSON (default: examples/simulation_trace.json)."""
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("examples/simulation_trace.json")
    )
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 65.0
    written = write_trace(path, seconds=seconds)
    print(f"wrote {written} ({written.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
