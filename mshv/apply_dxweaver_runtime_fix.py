#!/usr/bin/env python3
"""Post-patch hardening for the DXWeaver native MSHV control path.

Applied after apply_dxweaver_patch.py.  It fixes two live integration issues:
1) AUTO must be applied before AutoSeq / Multi Answer state.
2) the AutoSeq label's private mode index must be synchronized with HvTxW::s_mode
   before changing its state.

The transformation is asserted and fails closed if the expected patched source
is not present.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {label}: {path}")


def apply(root: Path) -> None:
    tx_cpp = root / "src/HvTxW/hvtxw.cpp"
    main_cpp = root / "src/main_ms.cpp"

    replace_once(
        tx_cpp,
        """void HvTxW::SetDxwAutoSeq(bool enabled)
{
    AutoSeqLab->SetAutoSeqState(enabled);
}
""",
        """void HvTxW::SetDxwAutoSeq(bool enabled)
{
    // Keep HvLabAutoSeq's private mode selector aligned with the real radio
    // mode before changing the per-mode AutoSeq flag.  In MA/hidden-label
    // paths this cannot be assumed from the UI state alone.
    AutoSeqLab->SetAutoSeqMode(s_mode,true);
    AutoSeqLab->SetAutoSeqState(enabled);
}
""",
        "synchronize native AutoSeq mode",
    )

    replace_once(
        main_cpp,
        """void Main_Ms::SetDxwAutomation(bool auto_enabled,bool auto_seq,bool multi_std)
{
    THvTxW->SetDxwAutoSeq(auto_seq);
    if (Multi_answer_mod_std->isChecked() != multi_std)
        Multi_answer_mod_std->setChecked(multi_std);
    if (THvTxW->GetAutoIsOn() != auto_enabled)
        THvTxW->auto_on();

    // Report what MSHV actually became, not what DXWeaver requested.
    THvTxW->SetDxwActualState(
        THvTxW->GetAutoIsOn(),
        THvTxW->GetDxwAutoSeq(),
        Multi_answer_mod_std->isChecked());
}
""",
        """void Main_Ms::SetDxwAutomation(bool auto_enabled,bool auto_seq,bool multi_std)
{
    // MSHV AUTO is the master state.  Apply it first because entering/leaving
    // AUTO may refresh dependent QSO/AutoSeq UI state.
    if (THvTxW->GetAutoIsOn() != auto_enabled)
        THvTxW->auto_on();

    // AutoSeq is per-mode in MSHV.  SetDxwAutoSeq synchronizes the internal
    // label mode with the current HvTxW mode before changing the flag.
    THvTxW->SetDxwAutoSeq(auto_seq);

    // MA Standard is valid only for the modes/activity types where upstream
    // MSHV itself enables it.  Never bypass contest/activity safety rules.
    bool ma_allowed = (s_mode==11 || s_mode==13 || s_mode==18 || allq65) && !g_block_mam;
    if (!multi_std)
    {
        if (Multi_answer_mod_std->isChecked())
            Multi_answer_mod_std->setChecked(false);
    }
    else if (ma_allowed)
    {
        Multi_answer_mod_std->setEnabled(true);
        if (!Multi_answer_mod_std->isChecked())
            Multi_answer_mod_std->setChecked(true);
    }

    // Report what MSHV actually became, not what DXWeaver requested.
    THvTxW->SetDxwActualState(
        THvTxW->GetAutoIsOn(),
        THvTxW->GetDxwAutoSeq(),
        Multi_answer_mod_std->isChecked());
}
""",
        "apply native automation in upstream-safe order",
    )

    print("DXWeaver native MSHV runtime hardening applied successfully")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    try:
        apply(root)
    except Exception as exc:
        print(f"RUNTIME FIX FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
