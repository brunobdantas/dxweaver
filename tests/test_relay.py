import socket
import time
from autoft8.transport import UdpRelay
from autoft8.fanout import UdpFanout
from autoft8 import protocol


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def recv_one(sock, timeout=2.0):
    sock.settimeout(timeout)
    return sock.recvfrom(65535)[0]


def test_relay_forwards_wsjt_and_plain_adif_unchanged():
    in_port = free_udp_port()
    out_port = free_udp_port()
    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sink.bind(("127.0.0.1", out_port))
    relay = UdpRelay("127.0.0.1", in_port, "127.0.0.1", out_port)
    relay.start()
    src = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        wsjt = protocol.build_heartbeat("MSHV", version="2.76")
        src.sendto(wsjt, ("127.0.0.1", in_port))
        assert recv_one(sink) == wsjt

        adif = b"<CALL:5>K1ABC <QSO_DATE:8>20260906 <TIME_ON:6>151500 <BAND:3>20M <MODE:3>FT8 <EOR>"
        src.sendto(adif, ("127.0.0.1", in_port))
        assert recv_one(sink) == adif

        for _ in range(20):
            st = relay.snapshot()
            if st["forwarded"] >= 2:
                break
            time.sleep(0.02)
        st = relay.snapshot()
        assert st["wsjt"] == 1
        assert st["adif"] == 1
        assert st["forwarded"] == 2
    finally:
        src.close(); relay.stop(); sink.close()


def test_relay_drops_unknown_by_default():
    in_port = free_udp_port(); out_port = free_udp_port()
    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sink.bind(("127.0.0.1", out_port)); sink.settimeout(0.25)
    relay = UdpRelay("127.0.0.1", in_port, "127.0.0.1", out_port)
    relay.start(); src = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        src.sendto(b"not ham data", ("127.0.0.1", in_port))
        try:
            sink.recvfrom(1024)
            assert False, "unknown datagram should not be forwarded"
        except socket.timeout:
            pass
    finally:
        src.close(); relay.stop(); sink.close()


def test_relay_snapshot_exposes_telemetry_fields():
    r = UdpRelay("127.0.0.1", 31001, "127.0.0.1", 31002)
    s = r.snapshot()
    assert s["enabled"] is True
    assert "latency_ms_avg" in s
    assert "jitter_ms" in s


def test_fanout_sends_primary_mshv_stream_to_gridtracker_unchanged():
    out_port = free_udp_port()
    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sink.bind(("127.0.0.1", out_port))
    f = UdpFanout("127.0.0.1", out_port)
    f.start()
    try:
        packet = protocol.build_heartbeat("MSHV", version="2.76")
        f.forward(packet, ("127.0.0.1", 2237))
        assert recv_one(sink) == packet
        st = f.snapshot()
        assert st["forwarded"] == 1
        assert st["forward"] == f"127.0.0.1:{out_port}"
    finally:
        f.stop(); sink.close()
