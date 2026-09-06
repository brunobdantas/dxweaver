"""WSJT-X/MSHV UDP protocol catalog used by DXWeaver.

DXWeaver keeps the standard WSJT-X schema-3 wire format.  For the companion
MSHV-DXWeaver build we append three booleans to Configure and Status.  The
protocol explicitly permits trailing fields, so ordinary WSJT-X/MSHV peers
silently ignore the extension.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .qdatastream import Reader, Writer, DecodeError, QUINT32_MAX, qtime_text

MAGIC = 0xADBCCBDA
SCHEMA = 3
HEARTBEAT=0; STATUS=1; DECODE=2; CLEAR=3; REPLY=4; QSO_LOGGED=5; CLOSE=6
REPLAY=7; HALT_TX=8; FREE_TEXT=9; WSPR_DECODE=10; LOCATION=11; LOGGED_ADIF=12
HIGHLIGHT_CALLSIGN=13; SWITCH_CONFIGURATION=14; CONFIGURE=15; ANNOTATION_INFO=16
TYPE_NAMES = {0:"Heartbeat",1:"Status",2:"Decode",3:"Clear",4:"Reply",5:"QSOLogged",6:"Close",7:"Replay",8:"HaltTx",9:"FreeText",10:"WSPRDecode",11:"Location",12:"LoggedADIF",13:"HighlightCallsign",14:"SwitchConfiguration",15:"Configure",16:"AnnotationInfo"}
SPECIAL_OP_MODES = {0:"NONE",1:"NA VHF",2:"EU VHF",3:"FIELD DAY",4:"RTTY RU",5:"WW DIGI",6:"FOX",7:"HOUND",8:"ARRL DIGI"}

@dataclass
class Message:
    type: int
    type_name: str
    id: str | None
    schema: int
    fields: dict = field(default_factory=dict)


def parse(data: bytes) -> Message:
    r = Reader(data)
    magic = r.u32()
    if magic != MAGIC:
        raise DecodeError(f"bad magic 0x{magic:08x}")
    schema = r.u32(); mtype = r.u32(); mid = r.utf8(); d: dict = {}
    try:
        if mtype == HEARTBEAT:
            d["max_schema"] = r.u32() if not r.at_end() else 2
            d["version"] = r.utf8() if not r.at_end() else None
            d["revision"] = r.utf8() if not r.at_end() else None
        elif mtype == STATUS:
            d["dial_frequency"] = r.u64(); d["mode"] = r.utf8(); d["dx_call"] = r.utf8()
            d["report"] = r.utf8(); d["tx_mode"] = r.utf8(); d["tx_enabled"] = r.boolean()
            d["transmitting"] = r.boolean(); d["decoding"] = r.boolean(); d["rx_df"] = r.u32()
            d["tx_df"] = r.u32(); d["de_call"] = r.utf8(); d["de_grid"] = r.utf8(); d["dx_grid"] = r.utf8()
            d["tx_watchdog"] = r.boolean(); d["sub_mode"] = r.utf8(); d["fast_mode"] = r.boolean()
            sop = r.u8(); d["special_operation_mode_value"] = sop; d["special_operation_mode"] = SPECIAL_OP_MODES.get(sop, f"UNKNOWN({sop})")
            ftol = r.u32(); trp = r.u32(); d["frequency_tolerance"] = None if ftol == QUINT32_MAX else ftol
            d["tr_period"] = None if trp == QUINT32_MAX else trp
            d["configuration_name"] = r.utf8(); d["tx_message"] = r.utf8()
            # MSHV-DXWeaver extension.  These fields are appended, never inserted.
            if not r.at_end():
                d["dxw_native_capable"] = r.boolean()
            if not r.at_end():
                d["dxw_auto_seq"] = r.boolean()
            if not r.at_end():
                d["dxw_multi_answer_std"] = r.boolean()
        elif mtype == DECODE:
            d["new"] = r.boolean(); d["time_ms"] = r.qtime(); d["time"] = qtime_text(d["time_ms"])
            d["snr"] = r.i32(); d["delta_time"] = r.double(); d["delta_frequency"] = r.u32()
            d["mode"] = r.utf8(); d["message"] = r.utf8(); d["low_confidence"] = r.boolean(); d["off_air"] = r.boolean()
        elif mtype == QSO_LOGGED:
            d["datetime_off"] = r.qdatetime(); d["dx_call"] = r.utf8(); d["dx_grid"] = r.utf8(); d["tx_frequency"] = r.u64()
            d["mode"] = r.utf8(); d["report_sent"] = r.utf8(); d["report_received"] = r.utf8(); d["tx_power"] = r.utf8()
            d["comments"] = r.utf8(); d["name"] = r.utf8(); d["datetime_on"] = r.qdatetime(); d["operator_call"] = r.utf8()
            d["my_call"] = r.utf8(); d["my_grid"] = r.utf8(); d["exchange_sent"] = r.utf8(); d["exchange_received"] = r.utf8()
            d["adif_propagation_mode"] = r.utf8()
        elif mtype == LOGGED_ADIF:
            d["adif_text"] = r.utf8()
    except DecodeError:
        # Older implementations may omit trailing fields. Keep the useful prefix.
        pass
    return Message(mtype, TYPE_NAMES.get(mtype, f"Unknown({mtype})"), mid, schema, d)


def _begin(mtype: int, instance_id: str, schema: int = SCHEMA) -> Writer:
    return Writer().u32(MAGIC).u32(schema).u32(mtype).utf8(instance_id)


def build_reply(instance_id: str, decode: dict, schema: int = SCHEMA, modifiers: int = 0) -> bytes:
    w = _begin(REPLY, instance_id, schema)
    w.qtime(decode.get("time_ms")); w.i32(int(decode.get("snr", 0))); w.double(float(decode.get("delta_time", 0.0)))
    w.u32(int(decode.get("delta_frequency", 0))); w.utf8(str(decode.get("mode") or "FT8")); w.utf8(str(decode.get("message") or ""))
    w.boolean(bool(decode.get("low_confidence", False))); w.u8(modifiers)
    return w.value()


def build_halt_tx(instance_id: str, auto_only: bool = True, schema: int = SCHEMA) -> bytes:
    return _begin(HALT_TX, instance_id, schema).boolean(auto_only).value()


def build_heartbeat(instance_id: str, version: str = "DXWeaver", schema: int = SCHEMA) -> bytes:
    return _begin(HEARTBEAT, instance_id, schema).u32(SCHEMA).utf8(version).utf8("").value()


def build_configure(
    instance_id: str,
    *,
    mode: str = "",
    frequency_tolerance: int = QUINT32_MAX,
    submode: str = "",
    fast_mode: bool = False,
    tr_period: int = QUINT32_MAX,
    rx_df: int = QUINT32_MAX,
    dx_call: str = "",
    dx_grid: str = "",
    generate_messages: bool = False,
    dxw_auto_enabled: bool = False,
    dxw_auto_seq: bool = False,
    dxw_multi_answer_std: bool = False,
    schema: int = SCHEMA,
) -> bytes:
    """Build Configure plus the optional MSHV-DXWeaver automation tail.

    The first nine fields are the standard WSJT-X Configure payload.  The final
    three booleans are understood only by the companion MSHV-DXWeaver build.
    They are intentionally trailing fields for backwards compatibility.
    """
    w = _begin(CONFIGURE, instance_id, schema)
    w.utf8(mode)
    w.u32(int(frequency_tolerance))
    w.utf8(submode)
    w.boolean(bool(fast_mode))
    w.u32(int(tr_period))
    w.u32(int(rx_df))
    w.utf8(dx_call)
    w.utf8(dx_grid)
    w.boolean(bool(generate_messages))
    w.boolean(bool(dxw_auto_enabled))
    w.boolean(bool(dxw_auto_seq))
    w.boolean(bool(dxw_multi_answer_std))
    return w.value()
