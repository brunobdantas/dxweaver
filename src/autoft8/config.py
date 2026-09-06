from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path


@dataclass
class ScoreWeights:
    watchlist: float = 2500
    incoming_caller: float = 1200
    new_entity: float = 1800
    new_entity_band: float = 900
    new_entity_mode: float = 500
    new_entity_slot: float = 1100
    new_call: float = 700
    new_band: float = 350
    new_mode: float = 200
    new_slot: float = 500
    new_grid: float = 120
    unconfirmed_slot: float = 180
    snr: float = 2.0
    low_confidence_penalty: float = 500


@dataclass
class Config:
    callsign: str = "PU2BRU"
    grid: str = ""
    listen_host: str = "127.0.0.1"
    listen_port: int = 2237
    multicast_group: str = ""

    # UDP relay: GridTracker -> DXWeaver -> WRL Desktop/Integrations App.
    relay_enabled: bool = True
    relay_listen_host: str = "127.0.0.1"
    relay_listen_port: int = 2238
    wrl_forward_host: str = "127.0.0.1"
    wrl_forward_port: int = 2239
    relay_forward_wsjt: bool = True
    relay_forward_adif: bool = True
    relay_forward_unknown: bool = False
    mode: str = "monitor"  # monitor | assist | auto
    operating_strategy: str = "both"  # hunt | answer | both
    selection_delay_sec: float = 0.45
    qso_timeout_sec: int = 150
    failure_cooldown_sec: int = 300
    worked_cooldown_sec: int = 86400
    max_qsos_per_hour: int = 20
    max_qsos_per_session: int = 200
    min_snr: int = -24
    max_snr: int = 20
    cq_only: bool = True
    answer_directed_after_cq_only: bool = True
    cq_response_window_sec: int = 45
    allowed_modes: list[str] = field(default_factory=lambda: ["FT8"])
    allowed_bands: list[str] = field(default_factory=list)
    allowed_special_operations: list[str] = field(default_factory=lambda: ["NONE"])
    excluded_calls: list[str] = field(default_factory=list)
    excluded_prefixes: list[str] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)

    # History sources
    adif_files: list[str] = field(default_factory=list)
    hrd_sqlite_files: list[str] = field(default_factory=list)
    auto_discover_hrd: bool = True
    history_refresh_sec: int = 30

    # DXCC/entity resolver. The cache can be updated from the official CTY.DAT URL.
    cty_file: str = "cty.dat"
    cty_auto_update: bool = True
    cty_update_max_age_days: int = 14
    cty_url: str = "https://www.country-files.com/cty/cty.dat"

    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787
    dry_run: bool = False
    halt_on_timeout: bool = True
    weights: ScoreWeights = field(default_factory=ScoreWeights)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        p = Path(path)
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        weights = ScoreWeights(**raw.pop("weights", {}))
        cfg = cls(**raw)
        cfg.weights = weights
        cfg.normalize()
        return cfg

    def normalize(self) -> None:
        self.callsign = self.callsign.upper().strip()
        self.grid = self.grid.upper().strip()
        self.mode = self.mode.lower().strip()
        self.operating_strategy = self.operating_strategy.lower().strip()
        self.allowed_modes = [x.upper().strip() for x in self.allowed_modes]
        self.allowed_bands = [x.lower().strip() for x in self.allowed_bands]
        self.allowed_special_operations = [x.upper().strip() for x in self.allowed_special_operations]
        self.excluded_calls = [x.upper().strip() for x in self.excluded_calls]
        self.excluded_prefixes = [x.upper().strip() for x in self.excluded_prefixes]
        self.watchlist = [x.upper().strip() for x in self.watchlist]
        if self.mode not in {"monitor", "assist", "auto"}:
            self.mode = "monitor"
        if self.operating_strategy not in {"hunt", "answer", "both"}:
            self.operating_strategy = "both"

    def save(self, path: str | Path) -> None:
        self.normalize()
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
