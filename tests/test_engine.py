import time
from autoft8.config import Config
from autoft8.adif import History
from autoft8.engine import Engine
from autoft8 import protocol
from autoft8.qdatastream import Writer

class FakeTransport:
    def __init__(self): self.sent=[]
    def send(self,data,addr): self.sent.append((protocol.parse(data),addr))

def msg_status():
    return protocol.Message(protocol.STATUS,'Status','MSHV',3,{'dial_frequency':14074000,'mode':'FT8','dx_call':'','transmitting':False,'special_operation_mode':'NONE'})
def msg_decode(call='K1ABC',snr=-10):
    return protocol.Message(protocol.DECODE,'Decode','MSHV',3,{'new':True,'time_ms':1000,'snr':snr,'delta_time':0.1,'delta_frequency':1000,'mode':'FT8','message':f'CQ {call} FN31','low_confidence':False,'off_air':False})

def test_engine_calls_best_candidate():
    cfg=Config(callsign='PU2BRU',mode='auto',selection_delay_sec=0.0); e=Engine(cfg,History()); t=FakeTransport(); e.attach_transport(t)
    a=('127.0.0.1',50000); e.on_message(msg_status(),a); e.on_message(msg_decode('K1AAA',-20),a); e.on_message(msg_decode('K1BBB',-5),a); e.tick()
    assert len(t.sent)==1; assert t.sent[0][0].type==protocol.REPLY; assert e.active_call=='K1BBB'


def test_dashboard_arm_switches_assist_to_auto():
    cfg = Config(mode="assist")
    e = Engine(cfg, History())
    e.set_armed(True)
    assert e.armed is True
    assert e.cfg.mode == "auto"
    e.set_armed(False)
    assert e.armed is False
    assert e.cfg.mode == "assist"


def test_runtime_strategy_and_limits():
    e = Engine(Config(), History())
    e.set_strategy("answer")
    e.set_limits(12, 55)
    s = e.snapshot()
    assert s["operating_strategy"] == "answer"
    assert s["limits"]["per_hour"] == 12
    assert s["limits"]["per_session"] == 55


def test_engine_accepts_fanout_attachment_and_exposes_it():
    class FakeFanout:
        def snapshot(self):
            return {"enabled": True, "forward": "127.0.0.1:2238", "forwarded": 0}

    e = Engine(Config(), History())
    f = FakeFanout()
    e.attach_fanout(f)
    assert e.fanout is f
    state = e.snapshot()
    assert state["fanout"]["enabled"] is True
    assert state["fanout"]["forward"] == "127.0.0.1:2238"
    assert state["version"] == "0.3.2"
