# DXWeaver 0.4.0

**FT8 decision automation + native MSHV control + UDP routing for GridTracker / WRL.**

DXWeaver is the external decision and integration layer. The companion **MSHV-DXWeaver** build remains the radio application and owns the live FT8 QSO state machine.

DXWeaver does not automate the mouse or scrape the screen. It uses the WSJT-X-compatible UDP protocol implemented by MSHV, adds a small trailing-field extension understood by the companion MSHV-DXWeaver build, ranks FT8 decodes, reads log history, routes UDP traffic and only selects the initial target when appropriate.

## 0.4.0 architecture

- **ANSWER** — delegated to MSHV Multi Answering Auto Seq Protocol Standard.
- **HUNT** — DXWeaver ranks CQ decodes and selects the initial target; MSHV owns the exchange after selection.
- **BOTH** — combines native MSHV answering with DXWeaver hunt selection.
- **Fail-closed ARM** — HUNT selection is blocked until MSHV-DXWeaver reports the actual applied AUTO + AutoSeq + Multi Answer state.
- **No UI click automation** — control is native UDP.

The custom MSHV extension is backwards-compatible at the wire level: DXWeaver appends three booleans to standard schema-3 Configure/Status messages. Ordinary implementations ignore trailing fields; MSHV-DXWeaver consumes them.

## Recommended PU2BRU topology

```text
MSHV-DXWeaver
    |
    | WSJT-X compatible UDP -> 127.0.0.1:2237
    v
DXWeaver
    |
    +----> GridTracker 127.0.0.1:2238
                     |
                     | Forward UDP -> 127.0.0.1:2239
                     v
               DXWeaver Relay
                     |
                     +----> WRL 127.0.0.1:2240

Ham Radio Deluxe Logbook remains an independent logging path.
```

Default config is supplied in `config.pu2bru-wrl.json`.

## Native safety handshake

When ARM or the operating strategy changes, DXWeaver requests native states from MSHV-DXWeaver. MSHV applies those values, reads back its actual internal state and only then sends Status acknowledgement.

DXWeaver compares requested versus reported values and refuses automatic HUNT selection while native confirmation is missing. The default configuration also keeps `allow_unconfirmed_native_control` disabled.

## Ranking and history

DXWeaver can use:

- ADIF history;
- Ham Radio Deluxe 6.9 SQLite history, read-only;
- CTY.DAT DXCC/entity data;
- worked call/band/mode/slot/grid history;
- watchlist / exclusions;
- SNR and confidence;
- cooldowns and hourly/session limits.

## WRL / GridTracker UDP router

The relay classifies incoming traffic as canonical WSJT-X/MSHV, plain ADIF, or unknown. WSJT-X and ADIF traffic are forwarded unchanged by default; unknown datagrams are dropped.

Default ports:

```text
MSHV-DXWeaver -> DXWeaver automation listener :2237
DXWeaver -> GridTracker                       :2238
GridTracker -> DXWeaver relay                 :2239
DXWeaver relay -> WRL                         :2240
```

## Windows installation

Two installers are produced:

```text
MSHV-DXWeaver-0.4.0-Setup.exe
DXWeaver-0.4.0-Setup.exe
```

Install **MSHV-DXWeaver first**, configure station identity/audio/CAT/PTT and its UDP destination as `127.0.0.1:2237`, then install DXWeaver.

DXWeaver is a per-user install and does not require Python. Its user configuration is stored at:

```text
%APPDATA%\DXWeaver\config.json
```

The local operator console is:

```text
http://127.0.0.1:8787
```

The default mode is **ASSIST / unarmed**. Verify native capability and confirmation in the dashboard before using ARM.

## Dashboard

The local dashboard provides:

- ARMED / DISARMED state;
- native requested versus confirmed MSHV state;
- HUNT / ANSWER / BOTH strategy;
- candidate ranking and selected target;
- current MSHV radio status;
- hourly/session limits;
- QSO/history information;
- GridTracker / WRL relay counters;
- HALT TX control.

## Build and test

Python test suite:

```bash
PYTHONPATH=src pytest -q
```

Windows DXWeaver installer:

```powershell
./scripts/build_windows.ps1
```

The MSHV-DXWeaver workflow clones the official MSHV source pinned to commit:

```text
8f93eb3e25056f0cb18699ef6c3bef3998c52cdf
```

It applies the asserted native-control patch, builds with Qt 5.15.2 / MinGW, stages the required runtime, launches the packaged executable for a Windows loader smoke test, and builds the Inno Setup installer.

## Licensing

DXWeaver's own code is MIT licensed.

MSHV-DXWeaver is a derivative of MSHV and is distributed under GPL-3.0. The CI produces the corresponding patch/source materials alongside the runtime build for license compliance.

## Operating responsibility

Automatic RF transmission remains under the licensed operator's responsibility. Validate callsign, band/frequency, power, CAT/PTT, audio levels, station limits and applicable regulations before arming automation.
