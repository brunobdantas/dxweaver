# Changelog

## 0.3.0 — DXWeaver

- Product renamed from Auto FT8 Manager to **DXWeaver**.
- Added transparent GridTracker -> DXWeaver -> WRL UDP router.
- Forwards canonical WSJT-X/MSHV protocol packets byte-for-byte.
- Forwards plain ADIF UDP broadcasts byte-for-byte.
- Unknown datagrams are blocked by default.
- Added loop prevention for identical local listen/forward endpoints.
- Added relay counters and errors to the dashboard.
- Added WRL relay to offline/self diagnostics.
- Added dedicated relay configuration independent from the automation listener.
- Documented dual-path architecture for reliable MSHV auto-replies plus GridTracker/WRL forwarding.
- Added Windows PyInstaller + Inno Setup build pipeline.
- Added GitHub Actions workflow that generates `DXWeaver-0.3.0-Setup.exe` and SHA-256 artifact.
- Added a development Windows installer/shortcut script.

## 0.2.0

- HRD 6.9 SQLite integration and auto-discovery.
- Live history refresh.
- DXCC/entity ranking with CTY.DAT.
- Confirmation-aware ranking.
- CQ-response automation.
- Hunt/answer/both strategies.
- Multicast support.
