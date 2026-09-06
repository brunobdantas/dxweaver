from __future__ import annotations
import json
import sqlite3
import tempfile
from pathlib import Path
from .config import Config
from .adif import History
from .cty import CtyResolver
from .ft8 import candidate_from_decode
from .history_sources import load_hrd_sqlite, discover_hrd_sqlite
from .engine import Engine
from . import protocol
from .transport import UdpRelay
import socket
import time


class _FakeTransport:
    def __init__(self): self.sent=[]
    def send(self, data, addr): self.sent.append((protocol.parse(data), addr))


def run_self_test(cfg: Config) -> tuple[bool, dict]:
    checks: dict[str, object] = {}
    ok = True
    try:
        fields = {"new":True,"time_ms":1000,"snr":-5,"delta_time":0.1,"delta_frequency":900,"mode":"FT8","message":"CQ K1ABC FN31","low_confidence":False,"off_air":False}
        reply = protocol.build_reply("MSHV", fields)
        checks["protocol_reply"] = protocol.parse(reply).type == protocol.REPLY
    except Exception as exc:
        checks["protocol_reply"] = f"FAIL: {exc}"; ok=False

    try:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.hrdsql"
            con=sqlite3.connect(p)
            con.execute("create table TABLE_HRD_CONTACTS_V01 (COL_CALL text,COL_BAND text,COL_MODE text,COL_GRIDSQUARE text,COL_COUNTRY text,COL_LOTW_QSL_RCVD text)")
            con.execute("insert into TABLE_HRD_CONTACTS_V01 values ('K1ABC','20m','FT8','FN31','United States','Y')")
            con.commit(); con.close()
            h=History(); rep=load_hrd_sqlite(p,h)
            checks["hrd_sqlite_reader"] = bool(rep.records == 1 and not rep.error and 'K1ABC' in h.calls)
            if not checks["hrd_sqlite_reader"]: ok=False
    except Exception as exc:
        checks["hrd_sqlite_reader"] = f"FAIL: {exc}"; ok=False

    try:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"cty.dat"
            p.write_text("Brazil: 11: 15: SA: -10.00: 53.00: 3.0: PY:\n    PP,PQ,PR,PS,PT,PU,PV,PW,PX,PY;\n",encoding="utf-8")
            r=CtyResolver(); r.load(p)
            ent=r.resolve(cfg.callsign or "PU2BRU")
            checks["cty_resolver"] = bool(ent)
            if not ent: ok=False
    except Exception as exc:
        checks["cty_resolver"] = f"FAIL: {exc}"; ok=False

    try:
        c=Config(callsign=cfg.callsign or "PU2BRU",mode="auto",operating_strategy="hunt",selection_delay_sec=0.0)
        e=Engine(c,History()); t=_FakeTransport(); e.attach_transport(t); addr=("127.0.0.1",50000)
        e.on_message(protocol.Message(protocol.STATUS,"Status","MSHV",3,{"dial_frequency":14074000,"mode":"FT8","dx_call":"","transmitting":False,"special_operation_mode":"NONE"}),addr)
        e.on_message(protocol.Message(protocol.DECODE,"Decode","MSHV",3,{"new":True,"time_ms":1000,"snr":-5,"delta_time":0.1,"delta_frequency":900,"mode":"FT8","message":"CQ K1ABC FN31","low_confidence":False,"off_air":False}),addr)
        e.tick()
        checks["decision_engine"] = bool(t.sent and t.sent[0][0].type == protocol.REPLY)
        if not checks["decision_engine"]: ok=False
    except Exception as exc:
        checks["decision_engine"] = f"FAIL: {exc}"; ok=False


    try:
        def free_port():
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close(); return port
        inp, outp = free_port(), free_port()
        sink=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sink.bind(("127.0.0.1",outp)); sink.settimeout(1.0)
        relay=UdpRelay("127.0.0.1",inp,"127.0.0.1",outp)
        relay.start(); src=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        adif=b"<CALL:5>K1ABC <QSO_DATE:8>20260906 <TIME_ON:6>151500 <BAND:3>20M <MODE:3>FT8 <EOR>"
        src.sendto(adif,("127.0.0.1",inp)); got=sink.recvfrom(65535)[0]
        checks["wrl_udp_relay"] = got == adif
        if not checks["wrl_udp_relay"]: ok=False
        src.close(); relay.stop(); sink.close()
    except Exception as exc:
        checks["wrl_udp_relay"] = f"FAIL: {exc}"; ok=False

    try:
        found=discover_hrd_sqlite() if cfg.auto_discover_hrd else []
        checks["hrd_detected_files"] = [str(x) for x in found]
    except Exception as exc:
        checks["hrd_detected_files"] = f"WARN: {exc}"

    checks["callsign"] = cfg.callsign
    checks["result"] = "PASS" if ok else "FAIL"
    return ok, checks


def print_self_test(cfg: Config) -> int:
    ok, checks = run_self_test(cfg)
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if ok else 2
