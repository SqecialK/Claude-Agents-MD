"""Operation: list currently discovered BTC Up/Down markets and fee schedules per venue.

    python operations/discover_markets.py [--config config/default.yaml]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from btcmm.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["discover", *sys.argv[1:]]))
