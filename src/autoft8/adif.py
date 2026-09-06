from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

TAG_RE = re.compile(r"<([A-Za-z0-9_]+):(\d+)(?::[^>]*)?>([^<]*)", re.I)
_TRUE = {"Y", "YES", "1", "TRUE", "T", "C"}


def parse_adif(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for chunk in re.split(r"<EOR\s*>", text, flags=re.I):
        rec: dict[str, str] = {}
        for m in TAG_RE.finditer(chunk):
            name, length, value = m.group(1).upper(), int(m.group(2)), m.group(3)
            rec[name] = value[:length].strip()
        if rec.get("CALL"):
            records.append(rec)
    return records


def _confirmed(rec: dict[str, str]) -> bool:
    for key in ("QSL_RCVD", "LOTW_QSL_RCVD", "EQSL_QSL_RCVD", "QRZCOM_QSO_UPLOAD_STATUS"):
        if str(rec.get(key, "")).upper() in _TRUE:
            return True
    return False


def _entity_from_record(rec: dict[str, str]) -> str:
    # Country name is stable across the history sources and matches CTY.DAT's entity name
    # better than ADIF numeric DXCC IDs do.
    return str(rec.get("COUNTRY") or rec.get("ENTITY") or "").strip()


@dataclass
class History:
    calls: set[str] = field(default_factory=set)
    call_bands: set[tuple[str, str]] = field(default_factory=set)
    call_modes: set[tuple[str, str]] = field(default_factory=set)
    slots: set[tuple[str, str, str]] = field(default_factory=set)
    grids: set[str] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)
    entity_bands: set[tuple[str, str]] = field(default_factory=set)
    entity_modes: set[tuple[str, str]] = field(default_factory=set)
    entity_slots: set[tuple[str, str, str]] = field(default_factory=set)
    confirmed_calls: set[str] = field(default_factory=set)
    confirmed_slots: set[tuple[str, str, str]] = field(default_factory=set)
    confirmed_entities: set[str] = field(default_factory=set)
    dxcc_ids: set[str] = field(default_factory=set)
    count: int = 0

    def add(
        self,
        call: str,
        band: str = "",
        mode: str = "FT8",
        grid: str = "",
        entity: str = "",
        dxcc: str = "",
        confirmed: bool = False,
    ) -> None:
        call = call.upper().strip()
        band = band.lower().strip()
        mode = mode.upper().strip()
        grid = grid.upper().strip()
        entity = entity.strip()
        dxcc = str(dxcc or "").strip()
        if not call:
            return
        self.calls.add(call)
        if band:
            self.call_bands.add((call, band))
        if mode:
            self.call_modes.add((call, mode))
        if band and mode:
            self.slots.add((call, band, mode))
        if grid:
            self.grids.add(grid[:4])
        if entity:
            self.entities.add(entity.casefold())
            if band:
                self.entity_bands.add((entity.casefold(), band))
            if mode:
                self.entity_modes.add((entity.casefold(), mode))
            if band and mode:
                self.entity_slots.add((entity.casefold(), band, mode))
        if dxcc:
            self.dxcc_ids.add(dxcc)
        if confirmed:
            self.confirmed_calls.add(call)
            if band and mode:
                self.confirmed_slots.add((call, band, mode))
            if entity:
                self.confirmed_entities.add(entity.casefold())
        self.count += 1

    def add_record(self, rec: dict[str, str]) -> None:
        self.add(
            rec.get("CALL", ""),
            rec.get("BAND", ""),
            rec.get("MODE", "FT8"),
            rec.get("GRIDSQUARE", rec.get("GRID", "")),
            _entity_from_record(rec),
            rec.get("DXCC", ""),
            _confirmed(rec),
        )

    def load_file(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        n0 = self.count
        for r in parse_adif(p.read_text(encoding="utf-8", errors="replace")):
            self.add_record(r)
        return self.count - n0

    def merge(self, other: "History") -> None:
        for name in (
            "calls", "call_bands", "call_modes", "slots", "grids", "entities",
            "entity_bands", "entity_modes", "entity_slots", "confirmed_calls",
            "confirmed_slots", "confirmed_entities", "dxcc_ids",
        ):
            getattr(self, name).update(getattr(other, name))
        self.count += other.count
