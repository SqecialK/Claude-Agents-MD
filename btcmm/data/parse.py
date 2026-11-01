"""Small, defensive parsing helpers shared by all adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def D(x: Any) -> Decimal:
    """Strict Decimal conversion. Floats go via ``str`` to avoid binary noise.
    Raises ValueError on garbage so bad venue data fails explicitly."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, dict) and "value" in x:  # PM US Amount {"value": "0.55", "currency": "USD"}
        x = x["value"]
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"not a decimal: {x!r}") from e


def D_or_none(x: Any) -> Decimal | None:
    if x is None or x == "":
        return None
    return D(x)


def first(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first present, non-None key. Venues have renamed fields
    (e.g. Kalshi cents -> *_dollars -> *_fp); we accept all known spellings."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def parse_ts(x: Any) -> datetime | None:
    """Parse ISO-8601 strings, epoch seconds, or epoch milliseconds to aware UTC."""
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    if isinstance(x, (int, float)) or (isinstance(x, str) and x.lstrip("-").isdigit()):
        v = float(x)
        if v > 1e14:  # microseconds
            v /= 1e6
        elif v > 1e11:  # milliseconds
            v /= 1e3
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(x).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Trim sub-microsecond precision (nanosecond timestamps) for fromisoformat.
    if "." in s:
        head, _, tail = s.partition(".")
        frac = "".join(ch for ch in tail if ch.isdigit())
        rest = tail[len(frac):]
        s = f"{head}.{frac[:6]}{rest}"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def window_minutes(start: datetime, end: datetime) -> int:
    return int(round((end - start).total_seconds() / 60.0))
