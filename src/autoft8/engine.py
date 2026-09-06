from __future__ import annotations
import logging
import threading
import time
from collections import deque
from .config import Config
from .adif import History
from .ft8 import candidate_from_decode, band_from_hz, parse_directed_to_me
from .scoring import eligible, score
from .cty import CtyResolver
from . import protocol

log = logging.getLogger("dxweaver.engine")


class Engine:
    def __init__(self, cfg: Config, history: History, resolver: CtyResolver | None = None):
        self.cfg = cfg
        self.history = history
        self.resolver = resolver
        self.transport = None
        self.fanout = None
        self.lock = threading.RLock()
        self.status: dict = {}
        self.instance = ""
        self.source_addr = None
        self.candidates: dict[tuple[str, str, str, str], object] = {}
        self.selection_at = 0.0

        # Explicit QSO state. active_kind is "cq" for a hunt we initiated and
        # "caller" when we answered a station calling us. A hunt is considered
        # engaged only after we decode a directed response from the target.
        self.active_call = ""
        self.active_kind = ""
        self.active_since = 0.0
        self.active_has_response = False
        self.active_last_rx = 0.0

        self.last_action = ""
        self.last_error = ""
        self.cooldowns: dict[str, float] = {}
        self.qso_times: deque[float] = deque()
        self.session_qsos = 0
        self.qso_log: deque[dict] = deque(maxlen=100)
        self.state_log: deque[dict] = deque(maxlen=50)
        self.connected_at = 0.0
        self.armed = cfg.mode == "auto"
        self.last_cq_activity = 0.0
        self.history_sources: list[dict] = []
        self.session_history = History()
        self.relay = None
        self.selected_candidate: dict = {}
        self.selected_at = 0.0
        self.last_cycle_candidates: list[dict] = []

    def attach_transport(self, t):
        self.transport = t

    def attach_fanout(self, fanout):
        self.fanout = fanout

    def attach_relay(self, relay):
        self.relay = relay

    def _event(self, text: str, now: float | None = None) -> None:
        ts = time.time() if now is None else now
        self.state_log.append({"time": ts, "event": text})
        log.info("STATE %s", text)

    def _clear_active(self, reason: str = "", now: float | None = None) -> None:
        old = self.active_call
        self.active_call = ""
        self.active_kind = ""
        self.active_since = 0.0
        self.active_has_response = False
        self.active_last_rx = 0.0
        if reason:
            self._event(f"release {old or '-'}: {reason}", now)

    def set_history_sources(self, reports) -> None:
        with self.lock:
            self.history_sources = [r.json() if hasattr(r, "json") else dict(r) for r in reports]

    def replace_history(self, history: History, reports=None) -> None:
        with self.lock:
            history.merge(self.session_history)
            self.history = history
            if reports is not None:
                self.set_history_sources(reports)
            self.last_action = f"history refreshed ({history.count} records)"
            log.info("History refreshed: %d records", history.count)

    def set_armed(self, value: bool):
        with self.lock:
            self.armed = bool(value)
            if self.armed:
                self.cfg.mode = "auto"
            elif self.cfg.mode == "auto":
                self.cfg.mode = "assist"
            self.last_action = "ARMED" if self.armed else "DISARMED"
            log.warning("Automation %s", "ARMED" if self.armed else "DISARMED")

    def set_strategy(self, strategy: str):
        strategy = str(strategy or "").strip().lower()
        if strategy not in {"hunt", "answer", "both"}:
            raise ValueError("strategy must be hunt, answer, or both")
        with self.lock:
            self.cfg.operating_strategy = strategy
            self.last_action = f"strategy {strategy}"

    def set_limits(self, per_hour=None, per_session=None):
        try:
            h = int(per_hour)
            s = int(per_session)
        except (TypeError, ValueError):
            raise ValueError("QSO limits must be integers")
        if not (1 <= h <= 999):
            raise ValueError("QSO/hour limit must be between 1 and 999")
        if not (1 <= s <= 9999):
            raise ValueError("session limit must be between 1 and 9999")
        with self.lock:
            self.cfg.max_qsos_per_hour = h
            self.cfg.max_qsos_per_session = s
            self.last_action = f"limits {h}/h, {s}/session"

    def halt(self):
        with self.lock:
            if self.transport and self.instance and self.source_addr:
                self.transport.send(protocol.build_halt_tx(self.instance, True), self.source_addr)
            self._clear_active("HALT TX")
            self.set_armed(False)
            self.last_action = "HALT TX + DISARM"

    def _note_cq_status(self, now: float) -> None:
        txmsg = str(self.status.get("tx_message") or "").upper().strip()
        if txmsg.startswith("CQ ") and self.cfg.callsign in txmsg:
            self.last_cq_activity = now

    def _strategy_accepts(self, kind: str) -> bool:
        strategy = self.cfg.operating_strategy
        if strategy == "hunt":
            return kind == "cq"
        if strategy == "answer":
            return kind == "caller"
        return kind in {"cq", "caller"}

    def _mark_directed_activity(self, message: str, now: float) -> None:
        directed = parse_directed_to_me(message, self.cfg.callsign)
        if not directed:
            return
        sender, payload = directed
        if self.active_call and sender == self.active_call:
            first = not self.active_has_response
            self.active_has_response = True
            self.active_last_rx = now
            if first:
                self._event(f"engaged {sender}: inbound {payload or 'directed message'}", now)

    def _caller_allowed_by_policy(self, now: float) -> bool:
        if self.cfg.directed_call_policy == "always":
            return True
        return bool(self.last_cq_activity and now - self.last_cq_activity <= self.cfg.cq_response_window_sec)

    def on_message(self, msg, addr):
        now = time.time()
        with self.lock:
            if msg.id:
                self.instance = msg.id
                self.source_addr = addr
            if not self.connected_at:
                self.connected_at = now
            if msg.type == protocol.STATUS:
                self.status = {"instance": msg.id, **msg.fields}
                self._note_cq_status(now)
                return
            if msg.type == protocol.DECODE:
                raw_message = str(msg.fields.get("message") or "").strip().upper()
                self._mark_directed_activity(raw_message, now)

                c = candidate_from_decode(
                    msg.fields, msg.id or self.instance, addr,
                    self.status.get("dial_frequency"), self.cfg.callsign,
                )
                if not c:
                    return
                if not self._strategy_accepts(c.kind):
                    return
                if c.kind == "caller" and not self._caller_allowed_by_policy(now):
                    return
                if self.resolver:
                    entity = self.resolver.resolve(c.call)
                    if entity:
                        c.entity = entity.name
                        c.entity_prefix = entity.main_prefix
                        c.continent = entity.continent
                ok, _ = eligible(c, self.cfg, self.cooldowns, now)
                if not ok:
                    return
                score(c, self.history, self.cfg)
                self.candidates[(c.call, c.band, c.mode, c.kind)] = c
                self.selection_at = now + self.cfg.selection_delay_sec
                return
            if msg.type == protocol.QSO_LOGGED:
                self._qso_logged(msg.fields, now)
                return
            if msg.type == protocol.CLOSE:
                self.last_action = "radio app closed"

    def _qso_logged(self, d: dict, now: float):
        call = str(d.get("dx_call") or self.active_call).upper()
        mode = str(d.get("mode") or self.status.get("mode") or "FT8").upper()
        grid = str(d.get("dx_grid") or "").upper()
        band = band_from_hz(d.get("tx_frequency") or self.status.get("dial_frequency"))
        entity_name = ""
        entity_prefix = ""
        if call and self.resolver:
            ent = self.resolver.resolve(call)
            if ent:
                entity_name = ent.name
                entity_prefix = ent.main_prefix
        if call:
            self.history.add(call, band, mode, grid, entity_name)
            self.session_history.add(call, band, mode, grid, entity_name)
            self.cooldowns[call] = now + self.cfg.worked_cooldown_sec
        self.qso_times.append(now)
        self.session_qsos += 1
        entry = {
            "time": now, "call": call, "band": band, "mode": mode, "grid": grid,
            "entity": entity_name, "entity_prefix": entity_prefix,
            "report_sent": d.get("report_sent"), "report_received": d.get("report_received"),
        }
        self.qso_log.append(entry)
        self._clear_active("QSO logged", now)
        self.last_action = f"QSO logged {call}"
        self.candidates.clear()
        log.info("QSO logged: %s %s %s", call, band, mode)

    def _limits_ok(self, now: float) -> tuple[bool, str]:
        while self.qso_times and self.qso_times[0] < now - 3600:
            self.qso_times.popleft()
        if len(self.qso_times) >= self.cfg.max_qsos_per_hour:
            return False, "hourly QSO limit"
        if self.session_qsos >= self.cfg.max_qsos_per_session:
            return False, "session QSO limit"
        return True, ""

    def _radio_idle(self, allow_existing_dx: bool = False) -> tuple[bool, str]:
        if not self.status:
            return False, "no Status"
        sop = str(self.status.get("special_operation_mode") or "NONE").upper()
        if sop not in self.cfg.allowed_special_operations:
            return False, f"special op {sop}"
        if self.status.get("transmitting"):
            return False, "transmitting"
        dx = str(self.status.get("dx_call") or "").strip().upper()
        if dx and not self.active_call and not allow_existing_dx:
            return False, f"operator QSO with {dx}"
        return True, ""

    def _rank_candidates(self):
        # In ANSWER/BOTH, a direct caller always outranks opportunistic hunt CQs.
        # Score and SNR remain the tie-breakers among candidates of the same kind.
        prefer_caller = self.cfg.operating_strategy in {"answer", "both"}
        return sorted(
            self.candidates.values(),
            key=lambda c: (1 if prefer_caller and c.kind == "caller" else 0, c.score, c.snr),
            reverse=True,
        )

    def _can_preempt_for(self, candidate) -> bool:
        return bool(
            self.cfg.preempt_hunt_for_caller
            and self.active_call
            and self.active_kind == "cq"
            and not self.active_has_response
            and candidate.kind == "caller"
            and candidate.call != self.active_call
        )

    def _active_timeout(self) -> int:
        if self.active_kind == "cq" and not self.active_has_response:
            return self.cfg.hunt_no_response_timeout_sec
        return self.cfg.qso_timeout_sec

    def tick(self):
        now = time.time()
        with self.lock:
            if self.active_call and now - self.active_since > self._active_timeout():
                call = self.active_call
                self.cooldowns[call] = now + self.cfg.failure_cooldown_sec
                if self.cfg.halt_on_timeout and self.transport and self.instance and self.source_addr:
                    self.transport.send(protocol.build_halt_tx(self.instance, True), self.source_addr)
                why = "no response" if self.active_kind == "cq" and not self.active_has_response else "QSO timeout"
                self._clear_active(why, now)
                self.last_action = f"timeout {call}: {why}"
                log.warning("QSO timeout %s (%s)", call, why)

            if not self.candidates or now < self.selection_at:
                return

            ranked = self._rank_candidates()
            self.last_cycle_candidates = [c.json() for c in ranked[:30]]
            if not ranked:
                self.candidates.clear()
                return
            best = ranked[0]

            # If a QSO is already active, only an explicit caller may preempt an
            # unanswered hunt attempt. Never switch once the hunted target has
            # answered us; MSHV Auto Seq owns the live exchange from then on.
            preempting = False
            if self.active_call:
                if not self._can_preempt_for(best):
                    self.candidates.clear()
                    return
                if self.status.get("transmitting"):
                    # Keep the caller queued until we are back in RX. Do not
                    # alter an in-progress transmit period.
                    self.selection_at = now + 0.2
                    return
                old = self.active_call
                self.cooldowns[old] = now + self.cfg.failure_cooldown_sec
                self._clear_active(f"preempted by directed caller {best.call}", now)
                preempting = True

            self.candidates.clear()
            self.selected_candidate = best.json()
            self.selected_at = now
            self.last_action = f"best {best.call} score={best.score:.0f}"

            if self.cfg.mode == "monitor":
                return
            if self.cfg.mode == "assist" or not self.armed:
                log.info("ASSIST best candidate: %s score %.0f (%s)", best.call, best.score, ", ".join(best.reasons))
                return

            ok, why = self._limits_ok(now)
            if not ok:
                self.last_action = why
                self.set_armed(False)
                return
            ok, why = self._radio_idle(allow_existing_dx=preempting)
            if not ok:
                self.last_action = f"not calling: {why}"
                return
            if not self.transport:
                return
            if self.cfg.dry_run:
                self.last_action = f"DRY RUN would call {best.call}"
                log.info(self.last_action)
                return

            self.transport.send(protocol.build_reply(best.instance, best.decode), best.source_addr)
            self.active_call = best.call
            self.active_kind = best.kind
            self.active_since = now
            # A caller candidate is already a decoded directed message to us,
            # therefore that QSO is engaged from the moment we answer it.
            self.active_has_response = best.kind == "caller"
            self.active_last_rx = now if best.kind == "caller" else 0.0
            self.cooldowns[best.call] = now + self.cfg.failure_cooldown_sec
            prefix = "ANSWER" if best.kind == "caller" else "CALL"
            self.last_action = f"{prefix} {best.call} score={best.score:.0f} ({best.kind})"
            self._event(f"{prefix.lower()} {best.call}", now)
            log.warning("AUTO %s %s score %.0f kind=%s", prefix, best.call, best.score, best.kind)

    def snapshot(self) -> dict:
        with self.lock:
            cs = sorted(self.candidates.values(), key=lambda c: c.score, reverse=True)[:30]
            now = time.time()
            return {
                "version": "0.3.3",
                "armed": self.armed,
                "mode": self.cfg.mode,
                "operating_strategy": self.cfg.operating_strategy,
                "instance": self.instance,
                "source_addr": self.source_addr,
                "status": self.status,
                "active_call": self.active_call,
                "active_kind": self.active_kind,
                "active_has_response": self.active_has_response,
                "active_for": round(now - self.active_since, 1) if self.active_since else 0,
                "active_last_rx_age": round(now - self.active_last_rx, 1) if self.active_last_rx else None,
                "session_qsos": self.session_qsos,
                "hour_qsos": len([x for x in self.qso_times if x >= now - 3600]),
                "history_qsos": self.history.count,
                "history_entities": len(self.history.entities),
                "history_sources": self.history_sources,
                "cty_entities": self.resolver.loaded_entities if self.resolver else 0,
                "cty_path": self.resolver.loaded_path if self.resolver else "",
                "last_cq_age": round(now - self.last_cq_activity, 1) if self.last_cq_activity else None,
                "candidates": [c.json() for c in cs],
                "last_cycle_candidates": self.last_cycle_candidates if self.selected_at and now - self.selected_at < 20 else [],
                "selected_candidate": self.selected_candidate if self.selected_at and now - self.selected_at < 20 else {},
                "selected_age": round(now - self.selected_at, 1) if self.selected_at else None,
                "last_action": self.last_action,
                "last_error": self.last_error,
                "state_log": list(self.state_log)[-20:],
                "qso_log": list(self.qso_log)[-20:],
                "transport": self.transport.snapshot() if self.transport and hasattr(self.transport, "snapshot") else {},
                "fanout": self.fanout.snapshot() if self.fanout and hasattr(self.fanout, "snapshot") else {"enabled": False},
                "relay": self.relay.snapshot() if self.relay else {"enabled": False},
                "limits": {
                    "per_hour": self.cfg.max_qsos_per_hour,
                    "per_session": self.cfg.max_qsos_per_session,
                    "qso_timeout_sec": self.cfg.qso_timeout_sec,
                    "hunt_no_response_timeout_sec": self.cfg.hunt_no_response_timeout_sec,
                },
                "decision_policy": {
                    "directed_call_policy": self.cfg.directed_call_policy,
                    "preempt_hunt_for_caller": self.cfg.preempt_hunt_for_caller,
                },
                "capabilities": {
                    "native_udp_reply": True,
                    "hunt_and_pounce": True,
                    "auto_answer_after_cq": True,
                    "directed_caller_preemption": True,
                    "qso_state_lock": True,
                    "auto_cq_start": False,
                    "auto_cq_reason": "Standard WSJT-X/MSHV UDP protocol has no native Enable-Tx/CQ-start command",
                },
            }
