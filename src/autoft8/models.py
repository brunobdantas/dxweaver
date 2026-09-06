from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class Candidate:
    call: str
    grid: str
    snr: int
    df: int
    dt: float
    mode: str
    message: str
    band: str
    instance: str
    source_addr: tuple[str, int]
    decode: dict[str, Any]
    low_confidence: bool = False
    kind: str = "cq"  # cq | caller
    entity: str = ""
    entity_prefix: str = ""
    continent: str = ""
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    seen_at: float = field(default_factory=time.time)

    def json(self) -> dict:
        return {
            "call": self.call,
            "grid": self.grid,
            "snr": self.snr,
            "df": self.df,
            "dt": self.dt,
            "mode": self.mode,
            "message": self.message,
            "band": self.band,
            "kind": self.kind,
            "entity": self.entity,
            "entity_prefix": self.entity_prefix,
            "continent": self.continent,
            "score": round(self.score, 1),
            "reasons": self.reasons,
            "seen_at": self.seen_at,
        }
