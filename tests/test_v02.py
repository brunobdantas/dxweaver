import sqlite3
import time
from pathlib import Path
from autoft8.config import Config
from autoft8.adif import History
from autoft8.cty import CtyResolver
from autoft8.ft8 import parse_directed_caller, candidate_from_decode
from autoft8.history_sources import load_hrd_sqlite
from autoft8.scoring import score
from autoft8.engine import Engine
from autoft8 import protocol


class FakeTransport:
    def __init__(self): self.sent=[]
    def send(self,data,addr): self.sent.append((protocol.parse(data),addr))


def test_directed_caller_parser():
    assert parse_directed_caller("PU2BRU K1ABC FN31", "PU2BRU") == ("K1ABC", "FN31")
    assert parse_directed_caller("PU2BRU K1ABC -10", "PU2BRU") is None
    assert parse_directed_caller("K1ABC PU2BRU FN31", "PU2BRU") is None


def test_cty_longest_prefix_and_exact(tmp_path: Path):
    p=tmp_path/'cty.dat'
    p.write_text(
        "Brazil: 11: 15: SA: -10.00: 53.00: 3.0: PY:\n"
        "    PP,PQ,PR,PS,PT,PU,PV,PW,PX,PY,=ZZ1SPECIAL;\n"
        "Argentina: 13: 14: SA: -34.80: 65.90: 3.0: LU:\n"
        "    AY,AZ,L0,L1,L2,L3,L4,L5,L6,L7,L8,L9,LO,LP,LQ,LR,LS,LT,LU,LW;\n",
        encoding='utf-8')
    r=CtyResolver(); assert r.load(p)==2
    assert r.resolve('PU2BRU').name=='Brazil'
    assert r.resolve('ZZ1SPECIAL').name=='Brazil'
    assert r.resolve('LU1ABC').name=='Argentina'


def test_hrd_sqlite_legacy_schema(tmp_path: Path):
    p=tmp_path/'mylog.hrdsql'
    con=sqlite3.connect(p)
    con.execute('create table TABLE_HRD_CONTACTS_V01 (COL_CALL text,COL_BAND text,COL_MODE text,COL_GRIDSQUARE text,COL_COUNTRY text,COL_DXCC text,COL_LOTW_QSL_RCVD text)')
    con.execute("insert into TABLE_HRD_CONTACTS_V01 values ('K1ABC','20m','FT8','FN31','United States','291','Y')")
    con.commit(); con.close()
    h=History(); rep=load_hrd_sqlite(p,h)
    assert not rep.error and rep.records==1 and rep.table=='TABLE_HRD_CONTACTS_V01'
    assert 'K1ABC' in h.calls and ('K1ABC','20m','FT8') in h.confirmed_slots
    assert 'united states' in h.entities


def test_entity_scoring():
    cfg=Config(callsign='PU2BRU'); h=History()
    fields={'new':True,'snr':-5,'delta_time':0.1,'delta_frequency':900,'mode':'FT8','message':'CQ K1ABC FN31','low_confidence':False,'off_air':False}
    c=candidate_from_decode(fields,'X',('127.0.0.1',1),14074000,'PU2BRU'); c.entity='United States'; c.entity_prefix='K'; c.continent='NA'
    score(c,h,cfg)
    assert 'new entity United States' in c.reasons and 'new entity slot' in c.reasons


def test_engine_answers_recent_cq_caller():
    cfg=Config(callsign='PU2BRU',mode='auto',operating_strategy='answer',selection_delay_sec=0.0,directed_call_policy='after_cq')
    e=Engine(cfg,History()); t=FakeTransport(); e.attach_transport(t); addr=('127.0.0.1',50000)
    status=protocol.Message(protocol.STATUS,'Status','MSHV',3,{'dial_frequency':14074000,'mode':'FT8','dx_call':'','transmitting':False,'special_operation_mode':'NONE','tx_message':'CQ PU2BRU GG66'})
    decode=protocol.Message(protocol.DECODE,'Decode','MSHV',3,{'new':True,'time_ms':1000,'snr':-9,'delta_time':0.1,'delta_frequency':800,'mode':'FT8','message':'PU2BRU K1ABC FN31','low_confidence':False,'off_air':False})
    e.on_message(status,addr); e.on_message(decode,addr); e.tick()
    assert len(t.sent)==1 and t.sent[0][0].type==protocol.REPLY and e.active_call=='K1ABC'


def test_engine_rejects_stale_directed_call_when_policy_is_after_cq():
    cfg=Config(callsign='PU2BRU',mode='auto',operating_strategy='answer',selection_delay_sec=0.0,directed_call_policy='after_cq',cq_response_window_sec=1)
    e=Engine(cfg,History()); t=FakeTransport(); e.attach_transport(t); addr=('127.0.0.1',50000)
    e.status={'dial_frequency':14074000,'mode':'FT8','dx_call':'','transmitting':False,'special_operation_mode':'NONE'}
    e.instance='MSHV'; e.source_addr=addr; e.last_cq_activity=time.time()-10
    decode=protocol.Message(protocol.DECODE,'Decode','MSHV',3,{'new':True,'time_ms':1000,'snr':-9,'delta_time':0.1,'delta_frequency':800,'mode':'FT8','message':'PU2BRU K1ABC FN31','low_confidence':False,'off_air':False})
    e.on_message(decode,addr); e.tick()
    assert not t.sent
