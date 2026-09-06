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

    # Primary MSHV/WSJT-X automation listener. Exactly one local application
    # should listen on this unicast endpoint.
    listen_host: str = "127.0.0.1"
    listen_port: int = 2237
    multicast_group: str = ""

    # Transparent one-way copy of the primary MSHV stream to GridTracker.
    gridtracker_forward_enabled: bool = True
    gridtracker_forward_host: str = "127.0.0.1"
    gridtracker_forward_port: int = 2238

    # UDP relay: GridTracker -> DXWeaver -> WRL Desktop/Integrations App.
    relay_enabled: bool = True
    relay_listen_host: str = "127.0.0.1"
    relay_listen_port: int = 2239
    wrl_forward_host: str = "127.0.0.1"
    wrl_forward_port: int = 2240
    relay_forward_wsjt: bool = True
    relay_forward_adif: bool = True
    relay_forward_unknown: bool = False

    mode: str = "monitor"  # monitor | assist | auto
    operating_strategy: str = "both"  # hunt | answer | both
    selection_delay_sec: float = 0.45

    # QSO state-machine timing. A hunt that has never received a directed
    # response is abandoned much sooner than a real exchange already underway.
    qso_timeout_sec: int = 150
    hunt_no_response_timeout_sec: int = 45
    preempt_hunt_for_caller: bool = True

    # Directed calls are accepted by default even when they were not preceded
    # by our own CQ. This is important when another station calls us while a
    # hunt attempt is still unanswered. Use "after_cq" for stricter behaviour.
    directed_call_policy: str = "always"  # always | after_cq
    failure_cooldown_sec: int = 300
    worked_cooldown_sec: int = 86400
    max_qsos_per_hour: int = 20
    max_qsos_per_session: int = 200
    min_snr: int = -24
    max_snr: int = 20
    cq_only: bool = True

    # Deprecated compatibility option from <= 0.3.2. Kept so existing config
    # files continue to load; directed_call_policy now controls this behaviour.
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

        # v0.3.0 used 2238 as the GridTracker->DXWeaver relay input and 2239
        # as the WRL target, while it had no DXWeaver->GridTracker fanout.
        # Migrate only the exact legacy default topology, preserving custom
        # operator port choices.
        legacy_030 = "gridtracker_forward_enabled" not in raw

        # v0.3.3 replaces the old CQ-window boolean with an explicit directed
        # call policy. Existing installs receive the safer operator-friendly
        # default: answer explicit calls to us even if they arrive during an
        # unanswered hunt attempt.
        legacy_directed_policy = "directed_call_policy" not in raw

        weights = ScoreWeights(**raw.pop("weights", {}))
        cfg = cls(**raw)
        cfg.weights = weights
        changed = False

        if legacy_030 and cfg.listen_port == 2237 and cfg.relay_listen_port == 2238 and cfg.wrl_forward_port == 2239:
            cfg.gridtracker_forward_enabled = True
            cfg.gridtracker_forward_host = "127.0.0.1"
            cfg.gridtracker_forward_port = 2238
            cfg.relay_listen_port = 2239
            cfg.wrl_forward_port = 2240
            changed = True

        if legacy_directed_policy:
            cfg.directed_call_policy = "always"
            changed = True

        cfg.normalize()
        if changed:
            try:
                cfg.save(p)
            except OSError:
                pass
        return cfg

    def normalize(self) -> None:
        self.callsign = self.callsign.upper().strip()
        self.grid = self.grid.upper().strip()
        self.mode = self.mode.lower().strip()
        self.operating_strategy = self.operating_strategy.lower().strip()
        self.directed_call_policy = self.directed_call_policy.lower().strip()
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
        if self.directed_call_policy not in {"always", "after_cq"}:
            self.directed_call_policy = "always"
        self.hunt_no_response_timeout_sec = max(15, int(self.hunt_no_response_timeout_sec))

    def save(self, path: str | Path) -> None:
        self.normalize()
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
