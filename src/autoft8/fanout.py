from __future__ import annotations
import socket
import threading
import time


class UdpFanout:
    """One-way transparent UDP fanout for MSHV/WSJT-X -> GridTracker.

    This socket does not bind to a listening port, so GridTracker can be the
    single listener on its own port. Every datagram received by DXWeaver's
    automation listener is forwarded byte-for-byte to the configured target.
    """

    def __init__(self, forward_host: str, forward_port: int):
        self.forward_host = forward_host
        self.forward_port = int(forward_port)
        self.sock: socket.socket | None = None
        self.lock = threading.RLock()
        self.stats = {
            "forwarded": 0,
            "bytes_forwarded": 0,
            "last_forward_at": None,
            "last_error": "",
            "last_source": None,
        }

    def start(self) -> None:
        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def forward(self, data: bytes, source_addr=None) -> None:
        if not self.sock:
            self.start()
        try:
            assert self.sock is not None
            self.sock.sendto(data, (self.forward_host, self.forward_port))
            with self.lock:
                self.stats["forwarded"] += 1
                self.stats["bytes_forwarded"] += len(data)
                self.stats["last_forward_at"] = time.time()
                self.stats["last_error"] = ""
                self.stats["last_source"] = source_addr
        except OSError as exc:
            with self.lock:
                self.stats["last_error"] = str(exc)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                **self.stats,
                "enabled": True,
                "forward": f"{self.forward_host}:{self.forward_port}",
            }

    def stop(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
