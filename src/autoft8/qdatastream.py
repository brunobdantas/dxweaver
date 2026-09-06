"""Minimal Qt QDataStream codec used by WSJT-X/MSHV UDP protocol.

Adapted from the MIT-licensed wsjtx-mcp implementation by Stefan Brunner
(AE5VG). The protocol uses big-endian scalars and QByteArray strings.
"""
from __future__ import annotations

import struct
from datetime import date, datetime, timedelta, timezone

NULL_LENGTH = 0xFFFFFFFF
INVALID_QTIME = 0xFFFFFFFF
QUINT32_MAX = 0xFFFFFFFF
_JULIAN_DAY_UNIX_EPOCH = 2440588


class DecodeError(ValueError):
    pass


class Writer:
    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def value(self) -> bytes:
        return b"".join(self.parts)

    def u8(self, v: int): self.parts.append(struct.pack(">B", v & 0xFF)); return self
    def u32(self, v: int): self.parts.append(struct.pack(">I", v & 0xFFFFFFFF)); return self
    def u64(self, v: int): self.parts.append(struct.pack(">Q", v & 0xFFFFFFFFFFFFFFFF)); return self
    def i32(self, v: int): self.parts.append(struct.pack(">i", int(v))); return self
    def i64(self, v: int): self.parts.append(struct.pack(">q", int(v))); return self
    def boolean(self, v: bool): return self.u8(1 if v else 0)
    def double(self, v: float): self.parts.append(struct.pack(">d", float(v))); return self

    def utf8(self, v: str | None):
        if v is None:
            return self.u32(NULL_LENGTH)
        b = v.encode("utf-8")
        self.u32(len(b)); self.parts.append(b); return self

    def qtime(self, ms: int | None):
        return self.u32(INVALID_QTIME if ms is None else ms)


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def at_end(self) -> bool:
        return self.pos >= len(self.data)

    def _take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.data):
            raise DecodeError(f"truncated at {self.pos}: need {n}, have {len(self.data)-self.pos}")
        b = self.data[self.pos:end]
        self.pos = end
        return b

    def u8(self) -> int: return struct.unpack(">B", self._take(1))[0]
    def u32(self) -> int: return struct.unpack(">I", self._take(4))[0]
    def u64(self) -> int: return struct.unpack(">Q", self._take(8))[0]
    def i32(self) -> int: return struct.unpack(">i", self._take(4))[0]
    def i64(self) -> int: return struct.unpack(">q", self._take(8))[0]
    def boolean(self) -> bool: return self.u8() != 0
    def double(self) -> float: return struct.unpack(">d", self._take(8))[0]

    def utf8(self) -> str | None:
        n = self.u32()
        if n == NULL_LENGTH:
            return None
        return self._take(n).decode("utf-8", "replace")

    def qtime(self) -> int | None:
        ms = self.u32()
        return None if ms == INVALID_QTIME else ms

    def qdatetime(self) -> datetime | None:
        julian = self.i64()
        ms = self.u32()
        spec = self.u8()
        offset = self.i32() if spec == 2 else 0
        if julian == 0 or ms == INVALID_QTIME:
            return None
        days = julian - _JULIAN_DAY_UNIX_EPOCH
        base = datetime(1970, 1, 1) + timedelta(days=days, milliseconds=ms)
        if spec == 1:
            return base.replace(tzinfo=timezone.utc)
        if spec == 2:
            return base.replace(tzinfo=timezone(timedelta(seconds=offset)))
        return base


def qtime_text(ms: int | None) -> str | None:
    if ms is None:
        return None
    s = ms // 1000
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
