from __future__ import annotations
from .models import Candidate
from .adif import History
from .config import Config


def eligible(c: Candidate, cfg: Config, cooldowns: dict[str, float], now: float) -> tuple[bool, str]:
    call = c.call.upper()
    if call == cfg.callsign:
        return False, "own-call"
    if call in cfg.excluded_calls:
        return False, "excluded-call"
    if any(call.startswith(p) for p in cfg.excluded_prefixes):
        return False, "excluded-prefix"
    if c.mode not in cfg.allowed_modes:
        return False, "mode"
    if cfg.allowed_bands and c.band not in cfg.allowed_bands:
        return False, "band"
    if c.snr < cfg.min_snr or c.snr > cfg.max_snr:
        return False, "snr"
    if cooldowns.get(call, 0) > now:
        return False, "cooldown"
    if cfg.operating_strategy == "hunt" and c.kind != "cq":
        return False, "strategy"
    if cfg.operating_strategy == "answer" and c.kind != "caller":
        return False, "strategy"
    return True, ""


def score(c: Candidate, h: History, cfg: Config) -> Candidate:
    w = cfg.weights; s = 0.0; reasons: list[str] = []
    call = c.call.upper(); band = c.band.lower(); mode = c.mode.upper(); entity = c.entity.casefold()
    if call in cfg.watchlist:
        s += w.watchlist; reasons.append("watchlist")
    if c.kind == "caller":
        s += w.incoming_caller; reasons.append("calling me")
    if entity:
        if entity not in h.entities:
            s += w.new_entity; reasons.append(f"new entity {c.entity}")
        if band and (entity, band) not in h.entity_bands:
            s += w.new_entity_band; reasons.append("new entity band")
        if (entity, mode) not in h.entity_modes:
            s += w.new_entity_mode; reasons.append("new entity mode")
        if band and (entity, band, mode) not in h.entity_slots:
            s += w.new_entity_slot; reasons.append("new entity slot")
    if call not in h.calls:
        s += w.new_call; reasons.append("new call")
    if band and (call, band) not in h.call_bands:
        s += w.new_band; reasons.append("new band")
    if (call, mode) not in h.call_modes:
        s += w.new_mode; reasons.append("new mode")
    if band and (call, band, mode) not in h.slots:
        s += w.new_slot; reasons.append("new slot")
    elif band and (call, band, mode) not in h.confirmed_slots:
        s += w.unconfirmed_slot; reasons.append("slot unconfirmed")
    if c.grid and c.grid[:4] not in h.grids:
        s += w.new_grid; reasons.append("new grid")
    snr_component = (c.snr - cfg.min_snr) * w.snr
    s += snr_component; reasons.append(f"snr {c.snr:+d}")
    if c.low_confidence:
        s -= w.low_confidence_penalty; reasons.append("low confidence")
    c.score = s; c.reasons = reasons
    return c
