"""System clock verification.

Why this matters: markouts at 1s and the final-seconds cutoffs (20s/45s)
are only meaningful if our clock is right, and feed-to-feed latency is
measured as ``recv_ts - exchange_ts``. A 100 ms drift would silently bias
every latency and markout statistic.

Two independent checks:
1. ``chronyc tracking`` (or ``timedatectl``) if the host runs a sync daemon.
2. A direct SNTP query (RFC 4330) to several servers; we take the median
   offset to be robust to one bad server.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import socket
import statistics
import struct
import subprocess
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

NTP_EPOCH_DELTA = 2208988800  # seconds between 1900-01-01 and 1970-01-01


@dataclass(frozen=True)
class ClockReport:
    offset_ms: float | None  # server_time - local_time (positive => local is behind)
    servers_ok: int
    servers_tried: int
    chrony_offset_ms: float | None
    synced_daemon: bool
    max_drift_ms: float

    @property
    def ok(self) -> bool:
        offs = [o for o in (self.offset_ms, self.chrony_offset_ms) if o is not None]
        if not offs:
            return False  # unknown clock state is treated as unsafe
        return all(abs(o) <= self.max_drift_ms for o in offs)

    def describe(self) -> str:
        return (f"clock ok={self.ok} sntp_offset_ms={self.offset_ms} "
                f"({self.servers_ok}/{self.servers_tried} servers) chrony_offset_ms={self.chrony_offset_ms} "
                f"daemon_synced={self.synced_daemon} limit_ms={self.max_drift_ms}")


def _to_ntp(t: float) -> bytes:
    sec = int(t) + NTP_EPOCH_DELTA
    frac = int((t - int(t)) * 2**32)
    return struct.pack("!II", sec, frac)


def _from_ntp(b: bytes) -> float:
    sec, frac = struct.unpack("!II", b)
    return sec - NTP_EPOCH_DELTA + frac / 2**32


def build_request(t1: float) -> bytes:
    # LI=0, VN=4, Mode=3 (client); transmit timestamp at bytes 40..48.
    pkt = bytearray(48)
    pkt[0] = (0 << 6) | (4 << 3) | 3
    pkt[40:48] = _to_ntp(t1)
    return bytes(pkt)


def compute_offset(resp: bytes, t1: float, t4: float) -> float:
    """Standard NTP offset = ((t2 - t1) + (t3 - t4)) / 2, in seconds."""
    if len(resp) < 48:
        raise ValueError("short NTP response")
    mode = resp[0] & 0x7
    if mode not in (4, 5):
        raise ValueError(f"unexpected NTP mode {mode}")
    stratum = resp[1]
    if stratum == 0:
        raise ValueError("kiss-of-death / unsynchronised server")
    t2 = _from_ntp(resp[32:40])
    t3 = _from_ntp(resp[40:48])
    return ((t2 - t1) + (t3 - t4)) / 2.0


def sntp_offset(server: str, timeout: float = 2.0) -> float:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = time.time()
        s.sendto(build_request(t1), (server, 123))
        resp, _ = s.recvfrom(512)
        t4 = time.time()
    return compute_offset(resp, t1, t4)


def parse_chrony_tracking(text: str) -> float | None:
    """Parse 'System time : 0.000012345 seconds slow of NTP time' -> ms offset
    expressed as server-minus-local (slow => positive)."""
    for line in text.splitlines():
        if line.strip().startswith("System time"):
            parts = line.split(":", 1)[1].split()
            val = float(parts[0]) * 1000.0
            return val if "slow" in line else -val
    return None


def chrony_offset_ms() -> tuple[float | None, bool]:
    if not shutil.which("chronyc"):
        return None, False
    try:
        out = subprocess.run(["chronyc", "tracking"], capture_output=True, text=True, timeout=3).stdout
    except (subprocess.SubprocessError, OSError):
        return None, False
    off = parse_chrony_tracking(out)
    synced = "Leap status     : Normal" in out
    return off, synced


def check_clock(servers: list[str], max_drift_ms: float) -> ClockReport:
    offsets = []
    for srv in servers:
        try:
            offsets.append(sntp_offset(srv) * 1000.0)
        except (OSError, ValueError) as e:
            log.warning("SNTP %s failed: %s", srv, e)
    chrony, synced = chrony_offset_ms()
    return ClockReport(
        offset_ms=statistics.median(offsets) if offsets else None,
        servers_ok=len(offsets), servers_tried=len(servers),
        chrony_offset_ms=chrony, synced_daemon=synced, max_drift_ms=max_drift_ms,
    )


async def check_clock_async(servers: list[str], max_drift_ms: float) -> ClockReport:
    return await asyncio.get_running_loop().run_in_executor(None, check_clock, servers, max_drift_ms)
