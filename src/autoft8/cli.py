from __future__ import annotations
import argparse
import logging
import signal
import time
import webbrowser
from .config import Config
from .engine import Engine
from .transport import UdpTransport, UdpRelay
from .fanout import UdpFanout
from .dashboard import Dashboard
from .history_sources import HistoryLoader
from .cty import CtyResolver, ensure_cty_file
from .diagnostics import print_self_test


def main(argv=None):
    ap = argparse.ArgumentParser(description="DXWeaver — FT8 automation and UDP log routing for MSHV/WSJT-X")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--arm", action="store_true", help="arm automatic calling for this run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true", help="run offline protocol/history/decision diagnostics and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = Config.load(args.config)
    cfg.dry_run = cfg.dry_run or args.dry_run
    if args.self_test:
        return print_self_test(cfg)

    loader = HistoryLoader(cfg.adif_files, cfg.hrd_sqlite_files, cfg.auto_discover_hrd)
    history = loader.load()
    for r in loader.last_reports:
        if r.error:
            logging.warning("History source %s: %s", r.path, r.error)
        else:
            logging.info("Loaded %s records from %s", r.records, r.path)

    resolver = CtyResolver()
    cty_path, cty_status = ensure_cty_file(cfg.cty_file, cfg.cty_url, cfg.cty_auto_update, cfg.cty_update_max_age_days)
    n_cty = resolver.load(cty_path)
    logging.info("CTY.DAT: %s; %s entities loaded from %s", cty_status, n_cty, cty_path)

    e = Engine(cfg, history, resolver)
    e.set_history_sources(loader.last_reports)
    if args.arm:
        cfg.mode = "auto"
        e.set_armed(True)

    fanout = None
    if cfg.gridtracker_forward_enabled:
        fanout = UdpFanout(cfg.gridtracker_forward_host, cfg.gridtracker_forward_port)
        e.attach_fanout(fanout)

    t = UdpTransport(
        cfg.listen_host,
        cfg.listen_port,
        e.on_message,
        raw_callback=fanout.forward if fanout else None,
        multicast_group=cfg.multicast_group,
    )
    e.attach_transport(t)

    relay = None
    if cfg.relay_enabled:
        relay = UdpRelay(cfg.relay_listen_host, cfg.relay_listen_port, cfg.wrl_forward_host, cfg.wrl_forward_port,
                         cfg.relay_forward_wsjt, cfg.relay_forward_adif, cfg.relay_forward_unknown)
        e.attach_relay(relay)

    d = Dashboard(e, cfg.dashboard_host, cfg.dashboard_port)
    try:
        if fanout:
            fanout.start()
        t.start()
        if relay:
            relay.start()
        d.start()
        url = f"http://{cfg.dashboard_host}:{cfg.dashboard_port}/"
        logging.info("Dashboard: %s", url)
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        stop = False
        def sig(*_):
            nonlocal stop; stop = True
        signal.signal(signal.SIGINT, sig); signal.signal(signal.SIGTERM, sig)
        next_history_check = time.time() + max(5, cfg.history_refresh_sec)
        while not stop:
            e.tick()
            now = time.time()
            if now >= next_history_check:
                next_history_check = now + max(5, cfg.history_refresh_sec)
                try:
                    refreshed = loader.load_if_changed()
                    if refreshed is not None:
                        e.replace_history(refreshed, loader.last_reports)
                except Exception:
                    logging.exception("History refresh failed")
            time.sleep(0.1)
    finally:
        try:
            e.set_armed(False)
        except Exception:
            pass
        d.stop()
        if relay:
            relay.stop()
        t.stop()
        if fanout:
            fanout.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
