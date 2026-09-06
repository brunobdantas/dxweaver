import time
from autoft8.qdatastream import Writer
from autoft8 import protocol
from autoft8.ft8 import parse_cq, parse_directed_to_me, band_from_hz
from autoft8.config import Config
from autoft8.adif import History
from autoft8.models import Candidate
from autoft8.scoring import score, eligible

def build_decode(msg="CQ K1ABC FN31", snr=-10, df=900):
    w=Writer().u32(protocol.MAGIC).u32(3).u32(protocol.DECODE).utf8("MSHV")
    w.boolean(True).qtime(12*3600*1000).i32(snr).double(0.1).u32(df).utf8("FT8").utf8(msg).boolean(False).boolean(False)
    return w.value()

def test_parse_decode_and_reply():
    m=protocol.parse(build_decode()); assert m.type==protocol.DECODE; assert m.fields['message']=='CQ K1ABC FN31'; assert m.fields['snr']==-10
    b=protocol.build_reply(m.id,m.fields); r=protocol.parse(b); assert r.type==protocol.REPLY

def test_cq_parser():
    assert parse_cq('CQ K1ABC FN31')==('K1ABC','FN31')
    assert parse_cq('CQ DX PY2ZZ GG66')==('PY2ZZ','GG66')
    assert band_from_hz(14074000)=='20m'

def test_directed_parser_tracks_full_qso_exchange():
    assert parse_directed_to_me('PU2BRU LU2DPG GF05', 'PU2BRU') == ('LU2DPG', 'GF05')
    assert parse_directed_to_me('PU2BRU LU2DPG -11', 'PU2BRU') == ('LU2DPG', '-11')
    assert parse_directed_to_me('PU2BRU LU2DPG R-09', 'PU2BRU') == ('LU2DPG', 'R-09')
    assert parse_directed_to_me('PU2BRU LU2DPG RR73', 'PU2BRU') == ('LU2DPG', 'RR73')
    assert parse_directed_to_me('TA2ANK LU2DPG -11', 'PU2BRU') is None

def test_scoring_prefers_new_slot():
    cfg=Config(callsign='PU2BRU'); h=History(); h.add('K1ABC','40m','FT8','FN31')
    c=Candidate('K1ABC','FN31',-5,1000,0.1,'FT8','CQ K1ABC FN31','20m','X',('127.0.0.1',1),{})
    score(c,h,cfg); assert 'new band' in c.reasons and 'new slot' in c.reasons

def test_cooldown():
    cfg=Config(); c=Candidate('K1ABC','FN31',-5,1000,0.1,'FT8','CQ K1ABC FN31','20m','X',('127.0.0.1',1),{})
    ok,_=eligible(c,cfg,{'K1ABC':time.time()+10},time.time()); assert not ok
