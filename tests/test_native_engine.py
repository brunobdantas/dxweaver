from autoft8 import protocol
from autoft8.adif import History
from autoft8.config import Config
from autoft8.native_engine import NativeEngine
from autoft8.qdatastream import Writer, QUINT32_MAX


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, data, addr):
        self.sent.append((data, addr))


def status_message(*, capable=True, auto=True, aseq=True, mastd=True, transmitting=False):
    return protocol.Message(
        protocol.STATUS,
        "Status",
        "MSHV",
        3,
        {
            "dial_frequency": 14074000,
            "mode": "FT8",
            "dx_call": "",
            "tx_enabled": auto,
            "transmitting": transmitting,
            "special_operation_mode": "NONE",
            "tx_message": "",
            "dxw_native_capable": capable,
            "dxw_auto_seq": aseq,
            "dxw_multi_answer_std": mastd,
        },
    )


def cq_message(call="K1ABC", snr=-10):
    return protocol.Message(
        protocol.DECODE,
        "Decode",
        "MSHV",
        3,
        {
            "new": True,
            "time_ms": 1000,
            "snr": snr,
            "delta_time": 0.1,
            "delta_frequency": 1000,
            "mode": "FT8",
            "message": f"CQ {call} FN31",
            "low_confidence": False,
            "off_air": False,
        },
    )


def direct_message(sender="LU2DPG", snr=-10):
    return protocol.Message(
        protocol.DECODE,
        "Decode",
        "MSHV",
        3,
        {
            "new": True,
            "time_ms": 1000,
            "snr": snr,
            "delta_time": 0.1,
            "delta_frequency": 1200,
            "mode": "FT8",
            "message": f"PU2BRU {sender} GF05",
            "low_confidence": False,
            "off_air": False,
        },
    )


def make_native(strategy="both"):
    cfg = Config(
        callsign="PU2BRU",
        control_backend="mshv_native",
        mode="auto",
        operating_strategy=strategy,
        selection_delay_sec=0.0,
        cty_auto_update=False,
    )
    e = NativeEngine(cfg, History())
    t = FakeTransport()
    e.attach_transport(t)
    addr = ("127.0.0.1", 50123)
    e.on_message(status_message(mastd=strategy in {"answer", "both"}), addr)
    return e, t, addr


def test_status_wire_extension_is_backward_compatible_tail():
    # Construct a real Status packet with standard fields followed by the three
    # MSHV-DXWeaver acknowledgement booleans.
    w = Writer().u32(protocol.MAGIC).u32(3).u32(protocol.STATUS).utf8("MSHV")
    w.u64(14074000).utf8("FT8").utf8("").utf8("").utf8("FT8")
    w.boolean(True).boolean(False).boolean(False)
    w.u32(0).u32(0).utf8("PU2BRU").utf8("GG66").utf8("")
    w.boolean(False).utf8("").boolean(False).u8(0)
    w.u32(QUINT32_MAX).u32(QUINT32_MAX).utf8("Default").utf8("")
    w.boolean(True).boolean(True).boolean(True)

    msg = protocol.parse(w.value())
    assert msg.type == protocol.STATUS
    assert msg.fields["dxw_native_capable"] is True
    assert msg.fields["dxw_auto_seq"] is True
    assert msg.fields["dxw_multi_answer_std"] is True


def test_arm_sends_native_configure_request():
    cfg = Config(control_backend="mshv_native", mode="assist", operating_strategy="both")
    e = NativeEngine(cfg, History())
    t = FakeTransport(); e.attach_transport(t)
    addr = ("127.0.0.1", 50123)
    e.on_message(status_message(auto=False, aseq=False, mastd=False), addr)
    t.sent.clear()

    e.set_armed(True)
    assert e.armed is True
    assert e.cfg.mode == "auto"
    assert t.sent
    assert protocol.parse(t.sent[-1][0]).type == protocol.CONFIGURE


def test_native_confirmation_is_required_before_hunt_reply():
    cfg = Config(
        callsign="PU2BRU", control_backend="mshv_native", mode="auto",
        operating_strategy="hunt", selection_delay_sec=0.0,
        native_mshv_required=True, allow_unconfirmed_native_control=False,
    )
    e = NativeEngine(cfg, History()); t = FakeTransport(); e.attach_transport(t)
    addr = ("127.0.0.1", 50123)
    e.on_message(status_message(capable=False, auto=True, aseq=False, mastd=False), addr)
    t.sent.clear()
    e.on_message(cq_message("TA2ANK"), addr)
    e.tick()
    assert not any(protocol.parse(data).type == protocol.REPLY for data, _ in t.sent)
    assert "not confirmed" in e.last_action.lower()


def test_hunt_only_selects_cq_after_native_confirmation():
    e, t, addr = make_native("hunt")
    assert e.native_confirmed is True
    t.sent.clear()
    e.on_message(cq_message("K1AAA", -20), addr)
    e.on_message(cq_message("K1BBB", -5), addr)
    e.tick()
    replies = [(data, a) for data, a in t.sent if protocol.parse(data).type == protocol.REPLY]
    assert len(replies) == 1
    assert "K1BBB" in e.last_action
    # Native backend does not create an external active-QSO lock.
    assert e.active_call == ""


def test_answer_never_replies_to_direct_caller_externally():
    e, t, addr = make_native("answer")
    t.sent.clear()
    e.on_message(direct_message("LU2DPG"), addr)
    e.tick()
    assert not any(protocol.parse(data).type == protocol.REPLY for data, _ in t.sent)
    assert "delegated to MSHV" in e.last_action


def test_both_direct_caller_is_delegated_not_preempted_by_python():
    e, t, addr = make_native("both")
    t.sent.clear()
    e.on_message(direct_message("LU2DPG", -4), addr)
    e.tick()
    assert not any(protocol.parse(data).type == protocol.REPLY for data, _ in t.sent)
    assert e.active_call == ""


def test_snapshot_distinguishes_requested_and_confirmed_native_state():
    e, _, _ = make_native("both")
    s = e.snapshot()
    assert s["control_backend"] == "mshv_native"
    assert s["native_control"]["capable"] is True
    assert s["native_control"]["confirmed"] is True
    assert s["native_control"]["requested"]["multi_answer_std"] is True
    assert s["native_control"]["reported"]["multi_answer_std"] is True
