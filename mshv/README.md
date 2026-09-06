# MSHV-DXWeaver native integration

DXWeaver 0.4+ delegates live FT8/FT4 QSO sequencing to MSHV instead of trying
to reproduce the radio application's state machine in an external Python
process.

## Upstream

The build is based on the official GPL-3.0 MSHV repository:

- Repository: `https://github.com/LZ2HV/MSHV`
- Pinned commit: `8f93eb3e25056f0cb18699ef6c3bef3998c52cdf`
- License: GNU GPL v3

The DXWeaver repository does **not** vendor an opaque copy of MSHV. CI clones
the pinned upstream commit and applies `apply_dxweaver_patch.py`. This keeps the
upstream provenance and our changes auditable.

## Why a native extension is necessary

The standard WSJT-X `Reply` UDP message is equivalent to selecting/double-clicking
a prior CQ/QRZ decode. It is useful for choosing the initial QSO partner but it
does not make an external companion the owner of the complete TX/RX/AutoSeq
lifecycle.

MSHV already contains:

- master AUTO state;
- per-mode AutoSeq state;
- Multi Answering Auto Seq Protocol Standard;
- message generation, TX/RX transitions, reports, RR73/73 and logging.

DXWeaver therefore asks MSHV to activate those existing native facilities and
uses its own scoring only to choose an initial CQ target in HUNT/BOTH mode.

## Wire extension

DXWeaver keeps the WSJT-X schema-3 `Configure` and `Status` messages. Extension
fields are appended at the end, which follows the protocol's forward/backward
compatibility rule for additional trailing fields.

### Configure (server -> MSHV-DXWeaver)

After the standard Configure fields:

1. `bool dxw_auto_enabled`
2. `bool dxw_auto_seq`
3. `bool dxw_multi_answer_std`

### Status (MSHV-DXWeaver -> server)

After standard `Tx Message`:

1. `bool dxw_native_capable` (always true in the custom build)
2. `bool dxw_auto_seq`
3. `bool dxw_multi_answer_std`

The standard Status `Tx Enabled` field is the acknowledgement for the actual
master AUTO state.

The DXWeaver cockpit does not report automation as confirmed until requested
and reported states agree.

## Native strategies

- `ANSWER`: MSHV Multi Answer Standard handles directed callers. DXWeaver never
  sends an external Reply to callers.
- `HUNT`: DXWeaver ranks CQs and uses standard Reply only to select the initial
  CQ after native AUTO + AutoSeq are confirmed. MSHV owns the exchange after
  selection.
- `BOTH`: Multi Answer remains active inside MSHV and DXWeaver may select an
  initial hunt CQ when the radio is idle.

## Building

The GitHub Actions workflow `mshv-native-windows.yml`:

1. clones the pinned MSHV upstream;
2. verifies its exact commit;
3. applies `apply_dxweaver_patch.py` (asserted transformations; fail closed);
4. builds the upstream `MSHV_WIN64.pro` with Qt/MinGW;
5. deploys required Qt runtime files;
6. publishes a portable `MSHV-DXWeaver-0.4.0-Windows.zip` artifact.

The generated MSHV-DXWeaver binary and derivative source changes remain GPL-3.0.
DXWeaver's separate Python companion remains MIT-licensed; the two programs
communicate over UDP and are distributed as separate artifacts.
