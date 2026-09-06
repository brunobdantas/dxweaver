# Research references used for architecture

## wsjtx-mcp
MIT-licensed, 2026. Strong reference for a pure-Python QDataStream codec and
WSJT-X UDP message catalog. The important design is to learn each application
instance ID and source UDP address from inbound packets, then send Reply/HaltTx
back to that exact address.

## MSHV
Official LZ2HV source confirms the WSJT-X-compatible UDP magic 0xADBCCBDA and
parses inbound Reply, Clear, Replay, HaltTx and Configure messages. Therefore a
single UDP companion can control both MSHV and WSJT-X.

## WSJT-Z
GPLv3 fork of WSJT-X with mature Auto Call/Auto CQ concepts. Used only as a
functional/UX reference, not copied.

## PyFT8
GPLv3 independent Python transceiver. Its QSO manager confirms the value of an
explicit QSO state machine, timeout handling, automatic reply progression and
ADIF history. Used only as an architectural reference, not copied.

## DXHunter
Current product/reference for enriching FTx decodes with logbook state and
ranking candidates (new DXCC/band/mode/slot, Most Wanted, then SNR). Public repo
currently exposes README/functionality but not reusable implementation source on
the default branch, so no code was copied.

## Ham Radio Deluxe 6.9
Official HRD documentation (2025-2026) confirms that Logbook 6.9 migrated from
Microsoft Access/ODBC to SQLite. The v6.9 database manager can import old logs,
and DXHunter documents direct use of the HRD SQLite database path. Auto FT8's
reader is read-only and performs schema introspection rather than assuming a
single hard-coded v6.9 table layout.

## CTY.DAT / Country Files
Entity resolution follows the standard AD1C CTY.DAT format. Runtime auto-update
is optional and can be disabled; the application keeps the data outside the
application source so DXCC/prefix data can be refreshed independently.
