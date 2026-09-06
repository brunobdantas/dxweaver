# Changelog

## 0.5.1 — Cockpit layout and dark UI corrective release

- Removed the floating `setGeometry` / `raise()` integration that allowed the DXWeaver controls to be covered by the MSHV waterfall/ruler.
- Attached the DXWeaver Control Panel directly to the existing `Main_Ms` master `QVBoxLayout` at index 0.
- Added a permanently visible **Candidates Matrix** at index 1, fed directly by the in-process `CandidateScorer` ranking.
- Matrix exposes score, New DXCC/Band/Mode/Slot, SNR, entity, CQ/ITU zones, distance, azimuth, history and target lock.
- Added application-wide `DxTheme.qss` using the DXWeaver dark design tokens and explicit ARM/HALT TX states.
- Added fail-closed Windows CI gates for layout ownership, absence of absolute panel geometry, Candidate Matrix wiring and packaged QSS resources.
- Bumped the unified native Windows installer/release to `DXWeaver-0.5.1-Setup.exe`.

## 0.5.0 — Unified native architecture

- Moved live FT8 QSO lifecycle ownership into the MSHV-derived native process.
- Added dynamic station callsign/grid identity updates and safe disarm on callsign changes while armed.
- Connected CTY.DAT entity/CQ/ITU intelligence and HRD/ADIF history cache to the native CandidateScorer.
- Preserved degraded scoring when history is unavailable and maintained strict C++11 compatibility for `dxw::` modules.
- Added full Windows build, CTest, GUI smoke test, GPL source bundle, Inno Setup and SHA-256 release gates.

## 0.4.0 — Native MSHV control

- Added companion **MSHV-DXWeaver** Windows build from official MSHV pinned to `8f93eb3e25056f0cb18699ef6c3bef3998c52cdf`.
- Added trailing-field schema-3 Configure/Status extension for native AUTO, AutoSeq and Multi Answer Standard control.
- Changed ANSWER mode to delegate live caller handling to MSHV Multi Answer AutoSeq.
- Changed HUNT/BOTH so DXWeaver selects only the initial CQ and MSHV owns the live FT8 exchange afterwards.
- Added fail-closed native capability/confirmation gating before automatic HUNT selection.
- Native acknowledgement now reports the **actual applied MSHV state**, not merely the requested state.
- Added deterministic Qt 5.15.2 / MinGW runtime packaging and Windows executable smoke test.
- Added `MSHV-DXWeaver-0.4.0-Setup.exe` Inno Setup installer.
- Added corresponding GPL patch/source packaging in CI.
- Finalized PU2BRU / GridTracker / WRL topology on ports 2237 -> 2238 -> 2239 -> 2240.
- DXWeaver Windows CI now runs 32 tests, executable self-test, PyInstaller packaging and Inno Setup compilation.

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
- Added GitHub Actions installer/SHA-256 artifact.
- Added a development Windows installer/shortcut script.

## 0.2.0

- HRD 6.9 SQLite integration and auto-discovery.
- Live history refresh.
- DXCC/entity ranking with CTY.DAT.
- Confirmation-aware ranking.
- CQ-response automation.
- Hunt/answer/both strategies.
- Multicast support.
