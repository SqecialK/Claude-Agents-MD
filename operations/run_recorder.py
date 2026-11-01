"""Operation: run the multi-venue data recorder until SIGINT/SIGTERM.

Deterministic wrapper around ``btcmm record``. Usage:
    python operations/run_recorder.py [--config config/default.yaml]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btcmm.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["record", *sys.argv[1:]]))
