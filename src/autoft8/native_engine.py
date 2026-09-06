from __future__ import annotations

import logging
import time

from . import protocol
from .engine import Engine
from . import __version__

log = logging.getLogger("dxweaver.native")


class NativeEngine(Engine):
    """DXWeaver engine for the companion MSHV-DXWeaver build.

    The old engine tried to own the complete FT8 QSO lifecycle outside MSHV.
    NativeEngine deliberately does not do that.  It asks MSHV to enable its
    internal AUTO / AutoSeq / Multi Answer Standard state and only performs the
    one operation that is useful outside the radio application: choosing which
    CQ should receive the initial standard Reply in HUNT/BOTH mode.

    Direct callers are never answered by DXWeaver in this backend.  They are
    left to MSHV's own Multi Answer AutoSeq state machine.
    """

    def __init__(self, cfg, history, resolver=None):
        super().__init__(cfg, history, resolver)
        self.native_last_sent = 0.0
        self.native_send_count = 0
        self.native_control_dirty = True
        self.native_confirmed = False
        self.native_capable = False
        self.native_last_confirmed = 0.0
        self.native_last_requested = {
            "auto_enabled": bool(self.armed),
            "auto_seq": bool(self.armed),
            "multi_answer_std": bool(self.armed and self.cfg.operating_strategy in {"answer", "both"}),
        }

    def _desired_native_flags(self) -> dict:
        enabled = bool(self.armed and self.cfg.mode == "auto")
        return {
            "auto_enabled": enabled,
            "auto_seq": enabled,
            "multi_answer_std": enabled and self.cfg.operating_strategy in {"answer", "both"},
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
            f"AUTO={int(desired['auto_enabled'])} ASeq={int(desired['auto_seq'])} "
            f"MAStd={int(desired['multi_answer_std'])}"
        )
        log.warning(self.last_action)
        return True

    def set_armed(self, value: bool):
        super().set_armed(value)
        self.native_control_dirty = True
        self.native_confirmed = False
        self._send_native_control(force=True)

    def set_strategy(self, strategy: str):
        super().set_strategy(strategy)
        self.native_control_dirty = True
        self.native_confirmed = False
        self._send_native_control(force=True)

    def on_message(self, msg, addr):
        super().on_message(msg, addr)
        with self.lock:
            if msg.type == protocol.STATUS:
                confirmed = self._status_confirms_native()
                if confirmed:
                    if not self.native_confirmed:
                        self._event("MSHV native automation confirmed")
                    self.native_confirmed = True
                    self.native_last_confirmed = time.time()
                    self.last_error = ""
                else:
                    self.native_confirmed = False
                    if self.cfg.native_mshv_required and self.armed:
                        if not self.native_capable:
                            self.last_error = "MSHV-DXWeaver native extension not detected"
                        else:
                            self.last_error = "waiting for MSHV native automation confirmation"
                    # A Status packet gives us a fresh source endpoint. Resend
                    # requested state when necessary, rate-limited by tick().
                    if self.native_control_dirty:
                        self._send_native_control(force=True)

    def _hunt_candidates(self):
        # ANSWER is completely native MSHV Multi Answer. BOTH/HUNT may choose a
        # CQ externally, but only the initial CQ. MSHV owns everything after it.
        if self.cfg.operating_strategy not in {"hunt", "both"}:
            return []
        return sorted(
            (c for c in self.candidates.values() if c.kind == "cq"),
            key=lambda c: (c.score, c.snr),
            reverse=True,
        )

    def tick(self):
        now = time.time()
        with self.lock:
            # Keep the native requested state converged with MSHV. Standard MSHV
            # will ignore the extension; in that case native_confirmed remains
            # false and no automatic Reply is sent.
            if self.native_control_dirty or (self.armed and not self.native_confirmed):
                self._send_native_control(force=False)

            if not self.candidates or now < self.selection_at:
                return

            all_ranked = sorted(self.candidates.values(), key=lambda c: (c.score, c.snr), reverse=True)
            self.last_cycle_candidates = [c.json() for c in all_ranked[:30]]
            hunt = self._hunt_candidates()

            # MSHV handles direct callers itself in ANSWER/BOTH. We retain the
            # candidates in the cockpit snapshot for visibility, but never send
            # Reply to them from the native backend.
            if not hunt:
                self.candidates.clear()
                if self.cfg.operating_strategy == "answer":
                    self.last_action = "ANSWER delegated to MSHV Multi Answer AutoSeq"
                return

            best = hunt[0]
            self.candidates.clear()
            self.selected_candidate = best.json()
            self.selected_at = now
            self.last_action = f"best hunt target {best.call} score={best.score:.0f}"

            if self.cfg.mode == "monitor":
                return
            if self.cfg.mode == "assist" or not self.armed:
                log.info("ASSIST native hunt target: %s score %.0f", best.call, best.score)
                return

            ok, why = self._limits_ok(now)
            if not ok:
                self.last_action = why
                self.set_armed(False)
                return

            if self.cfg.native_mshv_required and not self.native_confirmed and not self.cfg.allow_unconfirmed_native_control:
                self.last_action = "blocked: MSHV native automation not confirmed"
                return

            # MSHV must already be in native AUTO + AutoSeq before we select a
            # CQ.  That prevents a remote double-click from landing in an idle or
            # manually controlled state.
            if self.native_capable:
                if not bool(self.status.get("tx_enabled", False)):
                    self.last_action = "blocked: MSHV AUTO is not enabled"
                    return
                if not bool(self.status.get("dxw_auto_seq", False)):
                    self.last_action = "blocked: MSHV AutoSeq is not enabled"
                    return

            ok, why = self._radio_idle()
            if not ok:
                self.last_action = f"native hunt waiting: {why}"
                return
            if not self.transport:
                return
            if self.cfg.dry_run:
                self.last_action = f"DRY RUN would select {best.call} in MSHV"
                return

            # Standard Reply is used only as the equivalent of choosing the CQ.
            # From this instant on MSHV's internal AutoSeq owns the exchange.
            self.transport.send(protocol.build_reply(best.instance, best.decode), best.source_addr)
            self.cooldowns[best.call] = now + self.cfg.failure_cooldown_sec
            self.last_action = f"MSHV HUNT SELECT {best.call} score={best.score:.0f}"
            self._event(f"native hunt select {best.call}", now)
            log.warning(self.last_action)

    def snapshot(self) -> dict:
        data = super().snapshot()
        desired = self._desired_native_flags()
        data["version"] = __version__
        data["control_backend"] = "mshv_native"
        data["native_control"] = {
            "required": bool(self.cfg.native_mshv_required),
            "capable": bool(self.native_capable),
            "confirmed": bool(self.native_confirmed),
            "requested": desired,
            "reported": {
                "auto_enabled": bool(self.status.get("tx_enabled", False)),
                "auto_seq": bool(self.status.get("dxw_auto_seq", False)),
                "multi_answer_std": bool(self.status.get("dxw_multi_answer_std", False)),
            },
            "last_sent_at": self.native_last_sent or None,
            "last_confirmed_at": self.native_last_confirmed or None,
            "send_count": self.native_send_count,
        }
        return data
