from __future__ import annotations

import logging
import time

from . import protocol
from .engine import Engine
from . import __version__
from .ft8 import parse_directed_to_me

log = logging.getLogger("dxweaver.native")


class NativeEngine(Engine):
    """DXWeaver engine for the companion MSHV-DXWeaver build.

    MSHV owns the live FT8 exchange. DXWeaver only chooses the initial CQ for
    HUNT and coordinates which *native* MSHV automation profile should be
    active.

    Upstream MSHV deliberately disables the normal AutoSeq UI state while
    Multi Answer is active. Therefore ANSWER and HUNT are two distinct native
    profiles rather than three switches that can all be ON simultaneously:

      HUNT ready   = AUTO ON + AutoSeq ON + MA Standard OFF
      ANSWER ready = AUTO ON + AutoSeq OFF + MA Standard ON

    BOTH alternates safely between those profiles. It stays ANSWER-ready by
    default, temporarily enters HUNT-ready only when there is no directed
    caller and a CQ has been selected, then returns to ANSWER-ready after the
    hunted QSO is logged or times out.
    """

    def __init__(self, cfg, history, resolver=None):
        super().__init__(cfg, history, resolver)
        self.native_last_sent = 0.0
        self.native_send_count = 0
        self.native_control_dirty = True
        self.native_confirmed = False
        self.native_capable = False
        self.native_last_confirmed = 0.0

        self.native_phase = self._default_native_phase()
        self.native_pending_hunt = None
        self.native_hunt_in_progress = False
        self.native_hunt_call = ""
        self.native_hunt_deadline = 0.0
        self.native_hunt_engaged = False

        self.native_last_requested = self._desired_native_flags()

    def _default_native_phase(self) -> str:
        return "hunt" if self.cfg.operating_strategy == "hunt" else "answer"

    def _desired_native_flags(self) -> dict:
        enabled = bool(self.armed and self.cfg.mode == "auto")
        if not enabled:
            return {
                "auto_enabled": False,
                "auto_seq": False,
                "multi_answer_std": False,
            }

        strategy = self.cfg.operating_strategy
        hunt_profile = strategy == "hunt" or (strategy == "both" and self.native_phase == "hunt")
        if hunt_profile:
            return {
                "auto_enabled": True,
                "auto_seq": True,
                "multi_answer_std": False,
            }

        # ANSWER and the default phase of BOTH use MSHV Multi Answer Standard.
        # Upstream MSHV disables the normal AutoSeq UI while MA is active, so
        # AutoSeq OFF is expected here and must not be treated as a failure.
        return {
            "auto_enabled": True,
            "auto_seq": False,
            "multi_answer_std": True,
        }

    def _status_confirms_native(self) -> bool:
        desired = self._desired_native_flags()
        capable = bool(self.status.get("dxw_native_capable", False))
        self.native_capable = capable
        if not capable:
            return False
        return (
            bool(self.status.get("tx_enabled", False)) == desired["auto_enabled"]
            and bool(self.status.get("dxw_auto_seq", False)) == desired["auto_seq"]
            and bool(self.status.get("dxw_multi_answer_std", False)) == desired["multi_answer_std"]
        )

    def _send_native_control(self, force: bool = False) -> bool:
        desired = self._desired_native_flags()
        self.native_last_requested = dict(desired)
        now = time.time()
        if self.cfg.dry_run:
            self.native_control_dirty = False
            self.last_action = (
                "DRY RUN native control "
                f"phase={self.native_phase.upper()} "
                f"AUTO={int(desired['auto_enabled'])} ASeq={int(desired['auto_seq'])} "
                f"MAStd={int(desired['multi_answer_std'])}"
            )
            return False
        if not (self.transport and self.instance and self.source_addr):
            self.native_control_dirty = True
            return False
        if not force and now - self.native_last_sent < self.cfg.native_control_resend_sec:
            return False
        packet = protocol.build_configure(
            self.instance,
            dxw_auto_enabled=desired["auto_enabled"],
            dxw_auto_seq=desired["auto_seq"],
            dxw_multi_answer_std=desired["multi_answer_std"],
        )
        self.transport.send(packet, self.source_addr)
        self.native_last_sent = now
        self.native_send_count += 1
        self.native_control_dirty = False
        self.last_action = (
            "native control sent: "
            f"phase={self.native_phase.upper()} "
            f"AUTO={int(desired['auto_enabled'])} ASeq={int(desired['auto_seq'])} "
            f"MAStd={int(desired['multi_answer_std'])}"
        )
        log.warning(self.last_action)
        return True

    def _enter_native_phase(self, phase: str, reason: str = "", force: bool = True) -> None:
        if phase not in {"answer", "hunt"}:
            raise ValueError(f"invalid native phase {phase}")
        changed = self.native_phase != phase
        self.native_phase = phase
        self.native_control_dirty = True
        self.native_confirmed = False
        if reason:
            self.last_action = reason
        if changed or force:
            self._send_native_control(force=force)

    def _clear_native_hunt(self) -> None:
        self.native_pending_hunt = None
        self.native_hunt_in_progress = False
        self.native_hunt_call = ""
        self.native_hunt_deadline = 0.0
        self.native_hunt_engaged = False

    def _return_to_answer_profile(self, reason: str) -> None:
        self._clear_native_hunt()
        if self.cfg.operating_strategy == "both" and self.armed:
            self._enter_native_phase("answer", reason, force=True)

    def set_armed(self, value: bool):
        super().set_armed(value)
        self._clear_native_hunt()
        self.native_phase = self._default_native_phase()
        self.native_control_dirty = True
        self.native_confirmed = False
        self._send_native_control(force=True)

    def set_strategy(self, strategy: str):
        super().set_strategy(strategy)
        self._clear_native_hunt()
        self.native_phase = self._default_native_phase()
        self.native_control_dirty = True
        self.native_confirmed = False
        self._send_native_control(force=True)

    def on_message(self, msg, addr):
        super().on_message(msg, addr)
        now = time.time()
        with self.lock:
            if msg.type == protocol.STATUS:
                confirmed = self._status_confirms_native()
                if confirmed:
                    if not self.native_confirmed:
                        self._event(f"MSHV native {self.native_phase} profile confirmed")
                    self.native_confirmed = True
                    self.native_last_confirmed = now
                    self.last_error = ""
                else:
                    self.native_confirmed = False
                    if self.cfg.native_mshv_required and self.armed:
                        if not self.native_capable:
                            self.last_error = "MSHV-DXWeaver native extension not detected"
                        else:
                            self.last_error = f"waiting for MSHV native {self.native_phase} profile confirmation"
                    if self.native_control_dirty:
                        self._send_native_control(force=True)
                return

            if msg.type == protocol.DECODE and self.native_hunt_in_progress and self.native_hunt_call:
                raw = str(msg.fields.get("message") or "").strip().upper()
                directed = parse_directed_to_me(raw, self.cfg.callsign)
                if directed and directed[0] == self.native_hunt_call:
                    self.native_hunt_engaged = True
                    self.native_hunt_deadline = now + self.cfg.qso_timeout_sec
                    self.last_action = f"native hunt engaged {self.native_hunt_call}; MSHV owns QSO"

            if msg.type == protocol.QSO_LOGGED:
                if self.cfg.operating_strategy == "both" and self.native_phase == "hunt":
                    self._return_to_answer_profile("QSO logged; returning to ANSWER READY")
                return

            if msg.type == protocol.CLOSE:
                self.native_confirmed = False
                self.native_capable = False

    def _hunt_candidates(self):
        if self.cfg.operating_strategy not in {"hunt", "both"}:
            return []
        return sorted(
            (c for c in self.candidates.values() if c.kind == "cq"),
            key=lambda c: (c.score, c.snr),
            reverse=True,
        )

    def _direct_callers(self):
        return sorted(
            (c for c in self.candidates.values() if c.kind == "caller"),
            key=lambda c: (c.score, c.snr),
            reverse=True,
        )

    def _execute_hunt_candidate(self, best, now: float) -> bool:
        self.selected_candidate = best.json()
        self.selected_at = now
        self.last_action = f"best hunt target {best.call} score={best.score:.0f}"

        if self.cfg.mode == "monitor":
            return False
        if self.cfg.mode == "assist" or not self.armed:
            log.info("ASSIST native hunt target: %s score %.0f", best.call, best.score)
            return False

        ok, why = self._limits_ok(now)
        if not ok:
            self.last_action = why
            self.set_armed(False)
            return False

        if self.cfg.native_mshv_required and not self.native_confirmed and not self.cfg.allow_unconfirmed_native_control:
            self.last_action = f"blocked: MSHV native {self.native_phase} profile not confirmed"
            return False

        # A hunt selection is only valid in the HUNT native profile.
        if self.native_capable:
            if not bool(self.status.get("tx_enabled", False)):
                self.last_action = "blocked: MSHV AUTO is not enabled"
                return False
            if not bool(self.status.get("dxw_auto_seq", False)):
                self.last_action = "blocked: MSHV HUNT AutoSeq is not enabled"
                return False
            if bool(self.status.get("dxw_multi_answer_std", False)):
                self.last_action = "blocked: MSHV still in MA Standard profile"
                return False

        ok, why = self._radio_idle()
        if not ok:
            self.last_action = f"native hunt waiting: {why}"
            return False
        if not self.transport:
            return False
        if self.cfg.dry_run:
            self.last_action = f"DRY RUN would select {best.call} in MSHV"
            return False

        self.transport.send(protocol.build_reply(best.instance, best.decode), best.source_addr)
        self.cooldowns[best.call] = now + self.cfg.failure_cooldown_sec
        self.native_hunt_in_progress = True
        self.native_hunt_call = best.call
        self.native_hunt_engaged = False
        self.native_hunt_deadline = now + self.cfg.hunt_no_response_timeout_sec
        self.last_action = f"MSHV HUNT SELECT {best.call} score={best.score:.0f}"
        self._event(f"native hunt select {best.call}", now)
        log.warning(self.last_action)
        return True

    def tick(self):
        now = time.time()
        with self.lock:
            if self.native_hunt_in_progress and self.native_hunt_deadline and now >= self.native_hunt_deadline:
                call = self.native_hunt_call
                why = "QSO timeout" if self.native_hunt_engaged else "no response"
                if call:
                    self.cooldowns[call] = now + self.cfg.failure_cooldown_sec
                if self.cfg.halt_on_timeout and self.transport and self.instance and self.source_addr:
                    self.transport.send(protocol.build_halt_tx(self.instance, True), self.source_addr)
                if self.cfg.operating_strategy == "both":
                    self._return_to_answer_profile(f"hunt {call} {why}; returning to ANSWER READY")
                else:
                    self._clear_native_hunt()
                    self.last_action = f"hunt {call} {why}"
                return

            if self.native_control_dirty or (self.armed and not self.native_confirmed):
                self._send_native_control(force=False)

            # While a hunted QSO is live, MSHV owns the entire exchange.
            if self.native_hunt_in_progress:
                self.candidates.clear()
                return

            callers = self._direct_callers()

            # In BOTH, a caller directed to us always keeps/returns the radio to
            # ANSWER READY. Never start a hunt transition while a caller exists.
            if self.cfg.operating_strategy == "both" and callers:
                self.native_pending_hunt = None
                if self.native_phase != "answer":
                    self._enter_native_phase("answer", f"direct caller {callers[0].call}; switching to ANSWER READY", force=True)
                else:
                    self.last_action = f"caller {callers[0].call} delegated to MSHV MA Standard"
                self.candidates.clear()
                return

            if self.cfg.operating_strategy == "answer":
                if callers:
                    self.last_action = f"caller {callers[0].call} delegated to MSHV MA Standard"
                elif self.candidates:
                    self.last_action = "ANSWER delegated to MSHV Multi Answer Standard"
                self.candidates.clear()
                return

            # A BOTH hunt may already have a candidate parked while MSHV changes
            # from ANSWER READY to HUNT READY. Execute only after Status confirms.
            if self.native_pending_hunt is not None:
                if self.cfg.operating_strategy != "both" or self.native_phase != "hunt":
                    self.native_pending_hunt = None
                elif not self.native_confirmed:
                    return
                else:
                    best = self.native_pending_hunt
                    self.native_pending_hunt = None
                    self._execute_hunt_candidate(best, now)
                    return

            if not self.candidates or now < self.selection_at:
                return

            all_ranked = sorted(self.candidates.values(), key=lambda c: (c.score, c.snr), reverse=True)
            self.last_cycle_candidates = [c.json() for c in all_ranked[:30]]
            hunt = self._hunt_candidates()
            if not hunt:
                self.candidates.clear()
                return

            best = hunt[0]
            self.candidates.clear()

            if self.cfg.operating_strategy == "both" and self.native_phase != "hunt":
                self.native_pending_hunt = best
                self.selected_candidate = best.json()
                self.selected_at = now
                self._enter_native_phase(
                    "hunt",
                    f"CQ {best.call} selected; switching MSHV to HUNT READY",
                    force=True,
                )
                return

            self._execute_hunt_candidate(best, now)

    def snapshot(self) -> dict:
        data = super().snapshot()
        desired = self._desired_native_flags()
        data["version"] = __version__
        data["control_backend"] = "mshv_native"
        data["native_control"] = {
            "required": bool(self.cfg.native_mshv_required),
            "capable": bool(self.native_capable),
            "confirmed": bool(self.native_confirmed),
            "phase": self.native_phase,
            "phase_label": "HUNT READY" if self.native_phase == "hunt" else "ANSWER READY",
            "requested": desired,
            "reported": {
                "auto_enabled": bool(self.status.get("tx_enabled", False)),
                "auto_seq": bool(self.status.get("dxw_auto_seq", False)),
                "multi_answer_std": bool(self.status.get("dxw_multi_answer_std", False)),
            },
            "pending_hunt": self.native_pending_hunt.call if self.native_pending_hunt is not None else "",
            "hunt_in_progress": bool(self.native_hunt_in_progress),
            "hunt_call": self.native_hunt_call,
            "last_sent_at": self.native_last_sent or None,
            "last_confirmed_at": self.native_last_confirmed or None,
            "send_count": self.native_send_count,
        }
        return data
