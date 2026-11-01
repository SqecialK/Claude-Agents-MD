"""Command-line entry point.

    btcmm record      --config config/default.yaml   # start data collection
    btcmm discover    --config config/default.yaml   # list discovered markets + fees
    btcmm clock-check --config config/default.yaml   # verify clock sync (exit 1 if bad)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from btcmm.adapters import build_adapters
from btcmm.config import AppConfig, load_config
from btcmm.monitoring.clock import check_clock


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def cmd_clock(cfg: AppConfig) -> int:
    rep = check_clock(cfg.clock.ntp_servers, cfg.clock.max_drift_ms)
    print(rep.describe())
    return 0 if rep.ok else 1


async def _discover(cfg: AppConfig) -> int:
    rc = 0
    for a in build_adapters(cfg):
        try:
            ms = await a.discover_markets()
            print(f"== {a.venue.value}: {len(ms)} markets (credentials={'yes' if a.has_credentials else 'no'})")
            for m in sorted(ms, key=lambda m: m.window_end):
                print(f"  {m.market_id:<45} {m.window_minutes:>3}m  {m.window_start:%H:%M}-{m.window_end:%H:%M}Z  "
                      f"settle={m.settlement.kind.value}/{m.settlement.reference_index}"
                      f"{'' if m.settlement.parsed_confidently else ' [UNVERIFIED RULE]'}")
            if ms:
                fs = await a.get_fee_schedule(ms[0])
                print(f"  fees: type={fs.fee_type} taker={fs.taker_coef} maker={fs.maker_coef} "
                      f"rebate={fs.maker_rebate_coef} round={fs.rounding_increment}/{fs.rounding_scope} "
                      f"source={fs.source} verified={fs.verified}")
        except Exception as e:  # noqa: BLE001
            print(f"== {a.venue.value}: ERROR {type(e).__name__}: {e}")
            rc = 1
        finally:
            await a.aclose()
    return rc


async def _record(cfg: AppConfig) -> int:
    from btcmm.data.recorder import Recorder

    rep = check_clock(cfg.clock.ntp_servers, cfg.clock.max_drift_ms)
    logging.getLogger("btcmm").info(rep.describe())
    if not rep.ok and cfg.clock.block_recording_on_drift:
        print("refusing to record: clock check failed", file=sys.stderr)
        return 1
    rec = Recorder(cfg, build_adapters(cfg))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, rec.stop.set)
    await rec.run()
    print(f"recorder stopped; {rec.writer.records_written} records written")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="btcmm")
    p.add_argument("command", choices=["record", "discover", "clock-check"])
    p.add_argument("--config", default="config/default.yaml")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    _setup_logging(cfg.log_level)
    if args.command == "clock-check":
        return cmd_clock(cfg)
    if args.command == "discover":
        return asyncio.run(_discover(cfg))
    return asyncio.run(_record(cfg))


if __name__ == "__main__":
    sys.exit(main())
