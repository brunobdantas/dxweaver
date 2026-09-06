# PU2BRU — MSHV + GridTracker + DXWeaver + WRL

## Goal

```text
MSHV ───────────────► Ham Radio Deluxe Logbook
  │
  ├─ FT8 UDP ───────► GridTracker ──► DXWeaver ──► WRL
  │                       │
  └─ direct control ──────┴────────► DXWeaver automation engine
```

## Recommended ports

| Function | Address | Port |
|---|---|---:|
| MSHV FT8 stream (multicast) | 239.255.0.1 | 2237 |
| GridTracker -> DXWeaver relay | 127.0.0.1 | 2238 |
| DXWeaver -> WRL | 127.0.0.1 | 2239 |
| DXWeaver dashboard | 127.0.0.1 | 8787 |

## MSHV

In Network Configuration / UDP:

- UDP destination: `239.255.0.1`
- UDP port: `2237`
- accept/control UDP requests: enabled where applicable
- keep your existing Ham Radio Deluxe Logbook integration unchanged

MSHV can also keep its own Simple UDP Broadcast settings for other consumers;
DXWeaver does not require changing the HRD logging path.

## GridTracker

General:

- Receive UDP Messages: multicast `239.255.0.1`, port `2237`
- Forward UDP Messages: `127.0.0.1`, port `2238`, Enabled

Logging:

- if using the HRD Logbook/ADIF UDP target as the WRL bridge, point that output
  to `127.0.0.1:2238` as well.

## DXWeaver

Use `config.pu2bru-wrl.json` or configure:

- automation/control listener: multicast `239.255.0.1:2237`
- WRL relay listener: `127.0.0.1:2238`
- WRL destination: `127.0.0.1:2239`

Start in `assist` mode first.

## WRL Desktop / Integrations App

CAT Control & UDP / WSJT-X listener:

- Port: `2239`
- choose the desired WRL logbook
- Start Listening
- enable automatic listener startup if desired

Do not connect WRL directly to the rig for this logging-only path unless you
also intentionally want WRL CAT control.

## Validation

On DXWeaver dashboard, the WRL Router card should increase:

- `WSJT-X` while MSHV/GridTracker traffic flows;
- `ADIF` whenever GridTracker emits an ADIF UDP log record;
- `Forwarded` for both.

After a QSO is logged, confirm it appears in both HRD Logbook and WRL.
