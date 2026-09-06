import time
from autoft8.config import Config
from autoft8.adif import History
from autoft8.engine import Engine
from autoft8 import protocol


class FakeTransport:
    def __init__(self):
        self.sent=[]
    def send(self,data,addr):
        self.sent.append((protocol.parse(data),addr))


def msg_status(dx_call='', transmitting=False, tx_message=''):
    return protocol.Message(
        protocol.STATUS,'Status','MSHV',3,
        {'dial_frequency':14074000,'mode':'FT8','dx_call':dx_call,'transmitting':transmitting,
         'special_operation_mode':'NONE','tx_message':tx_message}
    )


def msg_decode(call='K1ABC',snr=-10):
    return protocol.Message(
        protocol.DECODE,'Decode','MSHV',3,
        {'new':True,'time_ms':1000,'snr':snr,'delta_time':0.1,'delta_frequency':1000,
         'mode':'FT8','message':f'CQ {call} FN31','low_confidence':False,'off_air':False}
    )


def msg_directed(sender='LU2DPG', payload='GF05', snr=-10):
    return protocol.Message(
        protocol.DECODE,'Decode','MSHV',3,
        {'new':True,'time_ms':1000,'snr':snr,'delta_time':0.1,'delta_frequency':1200,
         'mode':'FT8','message':f'PU2BRU {sender} {payload}','low_confidence':False,'off_air':False}
    )


def make_auto(strategy='both'):
    cfg=Config(callsign='PU2BRU',mode='auto',operating_strategy=strategy,selection_delay_sec=0.0,directed_call_policy='always')
    e=Engine(cfg,History()); t=FakeTransport(); e.attach_transport(t)
    a=('127.0.0.1',50000); e.on_message(msg_status(),a)
    return e,t,a


def test_engine_calls_best_candidate():
    e,t,a=make_auto('hunt')
    e.on_message(msg_decode('K1AAA',-20),a); e.on_message(msg_decode('K1BBB',-5),a); e.tick()
    assert len(t.sent)==1; assert t.sent[0][0].type==protocol.REPLY; assert e.active_call=='K1BBB'
    assert e.active_kind == 'cq'
    assert e.active_has_response is False


def test_both_prioritizes_directed_caller_over_cq():
    e,t,a=make_auto('both')
    e.on_message(msg_decode('TA2ANK',-3),a)
    e.on_message(msg_directed('LU2DPG','GF05',-11),a)
    e.tick()
    assert len(t.sent)==1
    assert e.active_call=='LU2DPG'
    assert e.active_kind=='caller'
    assert e.active_has_response is True


def test_directed_caller_preempts_unanswered_hunt():
    e,t,a=make_auto('both')
    e.on_message(msg_decode('TA2ANK',-15),a); e.tick()
    assert e.active_call=='TA2ANK' and e.active_has_response is False

    # This is the exact failure pattern seen on-air: another station calls us
    # while TA2ANK has never answered our hunt attempt.
    e.on_message(msg_directed('LU2DPG','GF05',-11),a); e.tick()
    assert len(t.sent)==2
    assert e.active_call=='LU2DPG'
    assert e.active_kind=='caller'
    assert e.active_has_response is True
    assert any('preempted by directed caller LU2DPG' in row['event'] for row in e.state_log)


def test_engaged_qso_is_never_preempted_by_other_caller():
    e,t,a=make_auto('both')
    e.on_message(msg_decode('TA2ANK',-15),a); e.tick()
    assert e.active_call=='TA2ANK'

    # TA2ANK actually answers us; from this point the exchange is locked.
    e.on_message(msg_directed('TA2ANK','-19',-15),a)
    assert e.active_has_response is True

    # Another caller must not steal the QSO mid-report/RR73 sequence.
    e.on_message(msg_directed('LU2DPG','GF05',-11),a); e.tick()
    assert e.active_call=='TA2ANK'
    assert len(t.sent)==1


def test_strategy_filters_are_enforced():
    hunt,t1,a1=make_auto('hunt')
    hunt.on_message(msg_directed('LU2DPG','GF05'),a1); hunt.tick()
    assert len(t1.sent)==0

    answer,t2,a2=make_auto('answer')
    answer.on_message(msg_decode('TA2ANK',-5),a2); answer.tick()
    assert len(t2.sent)==0
    answer.on_message(msg_directed('LU2DPG','GF05'),a2); answer.tick()
    assert answer.active_call=='LU2DPG'
    assert len(t2.sent)==1


def test_unanswered_hunt_uses_short_timeout():
    e,t,a=make_auto('hunt')
    e.cfg.hunt_no_response_timeout_sec=15
    e.on_message(msg_decode('TA2ANK',-15),a); e.tick()
    e.active_since=time.time()-16
    e.tick()
    assert e.active_call==''
    assert any(x[0].type==protocol.HALT_TX for x in t.sent)


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
    assert state["version"] == "0.3.3"
