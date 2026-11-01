"""Operation: verify system clock sync. Exits 0 if within max_drift_ms, else 1.

    python operations/clock_check.py [--config config/default.yaml]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btcmm.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["clock-check", *sys.argv[1:]]))
