"""WSJT-X/MSHV UDP protocol catalog (schema 3 subset needed by Auto FT8)."""
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


def build_heartbeat(instance_id: str, version: str = "AutoFT8", schema: int = SCHEMA) -> bytes:
    return _begin(HEARTBEAT, instance_id, schema).u32(SCHEMA).utf8(version).utf8("").value()
