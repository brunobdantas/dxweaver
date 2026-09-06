from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import os
import sqlite3
from .adif import History, parse_adif

log = logging.getLogger("autoft8.history")


@dataclass
class SourceReport:
    source: str
    kind: str
    records: int = 0
    path: str = ""
    table: str = ""
    error: str = ""

    def json(self) -> dict:
        return asdict(self)


ALIASES = {
    "CALL": ("COL_CALL", "CALL", "CALLSIGN", "DX_CALL"),
    "BAND": ("COL_BAND", "BAND"),
    "MODE": ("COL_MODE", "MODE", "SUBMODE"),
    "GRIDSQUARE": ("COL_GRIDSQUARE", "GRIDSQUARE", "GRID", "DX_GRID"),
    "COUNTRY": ("COL_COUNTRY", "COUNTRY", "ENTITY", "DXCC_NAME"),
    "DXCC": ("COL_DXCC", "DXCC", "DXCC_ID"),
    "QSL_RCVD": ("COL_QSL_RCVD", "QSL_RCVD"),
    "LOTW_QSL_RCVD": ("COL_LOTW_QSL_RCVD", "LOTW_QSL_RCVD", "LOTW_RCVD"),
    "EQSL_QSL_RCVD": ("COL_EQSL_QSL_RCVD", "EQSL_QSL_RCVD", "EQSL_RCVD"),
}


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _map_columns(columns: list[str]) -> dict[str, str]:
    by_upper = {c.upper(): c for c in columns}
    result: dict[str, str] = {}
    for standard, aliases in ALIASES.items():
        for alias in aliases:
            if alias in by_upper:
                result[standard] = by_upper[alias]
                break
    return result


def _pick_hrd_table(conn: sqlite3.Connection) -> tuple[str, dict[str, str]]:
    tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
    preferred = sorted(tables, key=lambda t: (0 if t.upper() == "TABLE_HRD_CONTACTS_V01" else 1, t))
    best: tuple[int, str, dict[str, str]] | None = None
    for table in preferred:
        try:
            columns = [r[1] for r in conn.execute(f"pragma table_info({_quote_ident(table)})")]
        except sqlite3.Error:
            continue
        mapping = _map_columns(columns)
        if "CALL" not in mapping:
            continue
        score = len(mapping) + (10 if table.upper() == "TABLE_HRD_CONTACTS_V01" else 0)
        if best is None or score > best[0]:
            best = (score, table, mapping)
    if not best:
        raise RuntimeError("No HRD QSO table with a recognizable callsign column was found")
    return best[1], best[2]


def load_hrd_sqlite(path: str | Path, history: History) -> SourceReport:
    p = Path(path).expanduser()
    report = SourceReport(source=p.name, kind="hrd-sqlite", path=str(p))
    if not p.exists():
        report.error = "file not found"; return report
    try:
        uri = p.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=3)
        try:
            table, mapping = _pick_hrd_table(conn); report.table = table
            selected = list(mapping.items())
            sql = "select " + ",".join(_quote_ident(actual) for _, actual in selected) + " from " + _quote_ident(table)
            n = 0
            for row in conn.execute(sql):
                rec = {standard: "" if value is None else str(value) for (standard, _), value in zip(selected, row)}
                history.add_record(rec); n += 1
            report.records = n
        finally:
            conn.close()
    except Exception as exc:
        report.error = str(exc)
    return report


def discover_hrd_sqlite() -> list[Path]:
    roots: list[Path] = []
    for env in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / "HRDLLC")
    if os.environ.get("USERPROFILE"):
        roots.extend([
            Path(os.environ["USERPROFILE"]) / "Documents" / "HRD Logbook",
            Path(os.environ["USERPROFILE"]) / "Documents" / "Ham Radio Deluxe",
        ])
    out: list[Path] = []
    seen: set[str] = set()
    patterns = ("*.hrdsql", "*.sqlite", "*.sqlite3", "*.db")
    for root in roots:
        if not root.exists():
            continue
        for pat in patterns:
            try:
                items = list(root.rglob(pat))
            except OSError:
                items = []
            for p in items[:100]:
                key = str(p.resolve()).casefold()
                if key not in seen:
                    seen.add(key); out.append(p)
    return out


class HistoryLoader:
    def __init__(self, adif_files: list[str], hrd_sqlite_files: list[str], auto_discover_hrd: bool = True):
        self.adif_files = list(adif_files)
        self.hrd_sqlite_files = list(hrd_sqlite_files)
        self.auto_discover_hrd = auto_discover_hrd
        self.last_reports: list[SourceReport] = []
        self._last_signature: tuple = ()

    def paths(self) -> tuple[list[Path], list[Path]]:
        adifs = [Path(x).expanduser() for x in self.adif_files]
        hrd = [Path(x).expanduser() for x in self.hrd_sqlite_files]
        if self.auto_discover_hrd:
            for p in discover_hrd_sqlite():
                if str(p.resolve()).casefold() not in {str(x.resolve()).casefold() for x in hrd if x.exists()}:
                    hrd.append(p)
        return adifs, hrd

    def signature(self) -> tuple:
        adifs, hrds = self.paths(); sig = []
        for p in [*adifs, *hrds]:
            try:
                st = p.stat(); sig.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                sig.append((str(p), 0, 0))
        return tuple(sig)

    def load(self) -> History:
        history = History(); reports: list[SourceReport] = []
        adifs, hrds = self.paths()
        for p in adifs:
            rep = SourceReport(source=p.name, kind="adif", path=str(p))
            try:
                if not p.exists():
                    rep.error = "file not found"
                else:
                    records = parse_adif(p.read_text(encoding="utf-8", errors="replace"))
                    for r in records: history.add_record(r)
                    rep.records = len(records)
            except Exception as exc:
                rep.error = str(exc)
            reports.append(rep)
        for p in hrds:
            reports.append(load_hrd_sqlite(p, history))
        self.last_reports = reports; self._last_signature = self.signature()
        return history

    def load_if_changed(self) -> History | None:
        sig = self.signature()
        if sig == self._last_signature:
            return None
        return self.load()
