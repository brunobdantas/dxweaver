from __future__ import annotations
import re
from .models import Candidate

CALL_RE = re.compile(r"^(?=.{3,15}$)(?=.*[A-Z])(?=.*\d)[A-Z0-9/]+$", re.I)
GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2})?$", re.I)
REPORT_RE = re.compile(r"^(?:R?[+-]\d{2}|RRR|RR73|73)$", re.I)


def looks_like_call(token: str) -> bool:
    t = token.strip("<>").upper()
    return bool(CALL_RE.match(t)) and not GRID_RE.match(t)


def parse_cq(message: str) -> tuple[str, str] | None:
    toks = message.upper().split()
    if not toks or toks[0] != "CQ":
        return None
    # Handles CQ CALL GRID, CQ DX CALL GRID, CQ POTA CALL GRID etc.
    for i in range(1, len(toks)):
        if looks_like_call(toks[i]):
            call = toks[i].strip("<>")
            grid = toks[i + 1] if i + 1 < len(toks) and GRID_RE.match(toks[i + 1]) else ""
            return call, grid
    return None


def parse_directed_to_me(message: str, my_call: str) -> tuple[str, str] | None:
    """Return ``(sender, payload)`` for an FT8 message addressed to us.

    Examples recognized as inbound traffic from K1ABC to PU2BRU::

        PU2BRU K1ABC FN31
        PU2BRU K1ABC -12
        PU2BRU K1ABC R-09
        PU2BRU K1ABC RR73
        PU2BRU K1ABC 73

    This parser is deliberately broader than candidate creation. It is used by
    the QSO state machine to know when a hunt target has actually answered us.
    """
    toks = message.upper().split()
    if len(toks) < 2 or toks[0].strip("<>") != my_call.upper().strip("<>"):
        return None
    if not looks_like_call(toks[1]):
        return None
    sender = toks[1].strip("<>")
    payload = toks[2].strip("<>") if len(toks) >= 3 else ""
    return sender, payload


def parse_directed_caller(message: str, my_call: str) -> tuple[str, str] | None:
    """Recognize an initial call to us: ``MYCALL CALLER GRID``.

    Reports/RR73/73 are not promoted to *new* candidates; once a QSO is active,
    MSHV's Auto Seq owns the report/RR73/73 exchange. The broader
    :func:`parse_directed_to_me` still observes those messages for state locking.
    """
    directed = parse_directed_to_me(message, my_call)
    if not directed:
        return None
    sender, payload = directed
    if GRID_RE.match(payload):
        return sender, payload
    return None


def band_from_hz(hz: int | float | None) -> str:
    if not hz:
        return ""
    mhz = float(hz) / 1_000_000.0
    bands = [
        (1.8, 2.0, "160m"), (3.5, 4.0, "80m"), (5.25, 5.45, "60m"), (7.0, 7.3, "40m"),
        (10.1, 10.15, "30m"), (14.0, 14.35, "20m"), (18.068, 18.168, "17m"), (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"), (28.0, 29.7, "10m"), (50.0, 54.0, "6m"), (144.0, 148.0, "2m"),
        (420.0, 450.0, "70cm"),
    ]
    for lo, hi, name in bands:
        if lo <= mhz <= hi:
            return name
    return ""


def candidate_from_decode(
    fields: dict,
    instance: str,
    addr: tuple[str, int],
    dial_frequency: int | None,
    my_call: str = "",
) -> Candidate | None:
    if not fields.get("new", True) or fields.get("off_air"):
        return None
    msg = str(fields.get("message") or "").strip().upper()
    parsed = parse_cq(msg)
    kind = "cq"
    if not parsed and my_call:
        parsed = parse_directed_caller(msg, my_call)
        kind = "caller"
    if not parsed:
        return None
    call, grid = parsed
    return Candidate(
        call=call, grid=grid, snr=int(fields.get("snr", 0)), df=int(fields.get("delta_frequency", 0)),
        dt=float(fields.get("delta_time", 0.0)), mode=str(fields.get("mode") or "FT8").upper(), message=msg,
        band=band_from_hz(dial_frequency), instance=instance, source_addr=addr, decode=fields,
        low_confidence=bool(fields.get("low_confidence", False)), kind=kind,
    )
