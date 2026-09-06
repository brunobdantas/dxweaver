from __future__ import annotations
import logging
import socket
import struct
import threading
import time
from typing import Callable
from . import protocol
from .qdatastream import DecodeError

log = logging.getLogger("dxweaver.udp")


class UdpTransport:
    def __init__(self, host: str, port: int, callback: Callable, raw_callback: Callable | None = None, multicast_group: str = ""):
        self.host = host
        self.port = port
        self.callback = callback
        self.raw_callback = raw_callback
        self.multicast_group = multicast_group.strip()
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.closed = False
        self.instances: dict[str, tuple[str, int]] = {}
        self.lock = threading.RLock()
        self.stats = {"received": 0, "parsed": 0, "invalid": 0, "bytes_received": 0, "last_rx_at": None, "last_from": None}

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        bind_host = "" if self.multicast_group else self.host
        s.bind((bind_host, self.port))
        if self.multicast_group:
            mreq = struct.pack("=4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(1.0)
        self.sock = s
        self.closed = False
        self.thread = threading.Thread(target=self._loop, daemon=True, name="dxweaver-udp")
        self.thread.start()
        log.info("UDP listening on %s:%s%s", bind_host or "0.0.0.0", self.port, f" multicast={self.multicast_group}" if self.multicast_group else "")

    def _loop(self):
        assert self.sock
        while not self.closed:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            with self.lock:
                self.stats["received"] += 1
                self.stats["bytes_received"] += len(data)
                self.stats["last_rx_at"] = time.time()
                self.stats["last_from"] = addr
            if self.raw_callback:
                try:
                    self.raw_callback(data, addr)
                except Exception:
                    log.exception("raw callback failed")
            try:
                msg = protocol.parse(data)
            except DecodeError:
                with self.lock:
                    self.stats["invalid"] += 1
                continue
            with self.lock:
                self.stats["parsed"] += 1
            if msg.id:
                self.instances[msg.id] = addr
            try:
                self.callback(msg, addr)
            except Exception:
                log.exception("message callback failed")

    def send(self, data: bytes, addr: tuple[str, int]):
        if not self.sock:
            raise RuntimeError("UDP transport not started")
        self.sock.sendto(data, addr)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                **self.stats,
                "listen": f"{self.host}:{self.port}",
                "multicast": self.multicast_group or None,
                "instances": len(self.instances),
            }

    def stop(self):
        self.closed = True
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


class UdpRelay:
    """Transparent UDP router for GridTracker -> WRL.

    Canonical WSJT-X protocol datagrams and plain ADIF UDP broadcasts are
    forwarded byte-for-byte.  Lightweight forwarding latency and inter-arrival
    jitter metrics are collected for the operator dashboard.
    """
    def __init__(self, listen_host: str, listen_port: int, forward_host: str, forward_port: int,
                 forward_wsjt: bool = True, forward_adif: bool = True, forward_unknown: bool = False):
        self.listen_host = listen_host
        self.listen_port = int(listen_port)
        self.forward_host = forward_host
        self.forward_port = int(forward_port)
        self.forward_wsjt = bool(forward_wsjt)
        self.forward_adif = bool(forward_adif)
        self.forward_unknown = bool(forward_unknown)
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.closed = False
        self.lock = threading.RLock()
        self.stats = {
            "received": 0, "forwarded": 0, "wsjt": 0, "adif": 0, "unknown": 0,
            "bytes_forwarded": 0, "last_type": "", "last_from": None,
            "last_forward_at": None, "last_error": "", "latency_ms_last": None,
            "latency_ms_avg": None, "jitter_ms": None,
        }
        self._last_rx_perf: float | None = None
        self._last_interval_ms: float | None = None

    @staticmethod
    def classify(data: bytes) -> str:
        if len(data) >= 4 and data[:4] == b"\xad\xbc\xcb\xda":
            return "wsjt"
        probe = data.lstrip().upper()
        if probe.startswith(b"<") and (b"<EOR>" in probe or b"<CALL:" in probe):
            return "adif"
        return "unknown"

    def start(self):
        if self.listen_port == self.forward_port and self.listen_host in {self.forward_host, "0.0.0.0", ""}:
            raise ValueError("relay listen and forward endpoints would create a UDP loop")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.listen_host, self.listen_port))
        s.settimeout(1.0)
        self.sock = s
        self.closed = False
        self.thread = threading.Thread(target=self._loop, daemon=True, name="dxweaver-relay")
        self.thread.start()
        log.info("WRL relay listening %s:%s -> %s:%s", self.listen_host, self.listen_port, self.forward_host, self.forward_port)

    def _loop(self):
        assert self.sock
        while not self.closed:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            rx_perf = time.perf_counter()
            kind = self.classify(data)
            with self.lock:
                self.stats["received"] += 1
                self.stats[kind] += 1
                self.stats["last_type"] = kind
                self.stats["last_from"] = addr
                if self._last_rx_perf is not None:
                    interval_ms = (rx_perf - self._last_rx_perf) * 1000.0
                    if self._last_interval_ms is not None:
                        variation = abs(interval_ms - self._last_interval_ms)
                        old_j = self.stats["jitter_ms"]
                        self.stats["jitter_ms"] = variation if old_j is None else (old_j * 0.85 + variation * 0.15)
                    self._last_interval_ms = interval_ms
                self._last_rx_perf = rx_perf
            allowed = ((kind == "wsjt" and self.forward_wsjt) or
                       (kind == "adif" and self.forward_adif) or
                       (kind == "unknown" and self.forward_unknown))
            if not allowed:
                continue
            try:
                started = time.perf_counter()
                self.sock.sendto(data, (self.forward_host, self.forward_port))
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                with self.lock:
                    self.stats["forwarded"] += 1
                    self.stats["bytes_forwarded"] += len(data)
                    self.stats["last_forward_at"] = time.time()
                    self.stats["last_error"] = ""
                    self.stats["latency_ms_last"] = elapsed_ms
                    old = self.stats["latency_ms_avg"]
                    self.stats["latency_ms_avg"] = elapsed_ms if old is None else (old * 0.85 + elapsed_ms * 0.15)
            except OSError as exc:
                with self.lock:
                    self.stats["last_error"] = str(exc)
                log.exception("WRL relay forward failed")

    def snapshot(self) -> dict:
        with self.lock:
            return {
                **self.stats,
                "enabled": True,
                "listen": f"{self.listen_host}:{self.listen_port}",
                "forward": f"{self.forward_host}:{self.forward_port}",
                "enabled_types": {
                    "wsjt": self.forward_wsjt,
                    "adif": self.forward_adif,
                    "unknown": self.forward_unknown,
                },
            }

    def stop(self):
        self.closed = True
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
