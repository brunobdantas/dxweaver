#!/usr/bin/env python3
"""Build-time integration patch for DXWeaver 0.5.0.

The official MSHV source remains the GPL-3.0 DSP/radio foundation. This patch
injects DXWeaver's in-process automation core and native safety HUD, removes
the external UDP control dependency from the automation path, and renames the
produced application to DXWeaver. It is pinned and fail-closed against one
audited upstream commit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

PINNED_UPSTREAM = "8f93eb3e25056f0cb18699ef6c3bef3998c52cdf"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {label}: {path}")


def verify_commit(root: Path) -> None:
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != PINNED_UPSTREAM:
        raise RuntimeError(f"unexpected MSHV commit {actual}; expected {PINNED_UPSTREAM}")


def copy_native_sources(repo: Path, upstream: Path) -> None:
    dst_core = upstream / "src/native/dxw"
    dst_bridge = upstream / "src/native/mshv_bridge"
    dst_core.mkdir(parents=True, exist_ok=True)
    dst_bridge.mkdir(parents=True, exist_ok=True)
    for src in (repo / "src/native/dxw").glob("*.[hc]*"):
        shutil.copy2(src, dst_core / src.name)
    for src in (repo / "src/native/mshv_bridge").glob("*.[hc]*"):
        shutil.copy2(src, dst_bridge / src.name)


def apply(upstream: Path) -> None:
    verify_commit(upstream)
    repo = Path(__file__).resolve().parents[1]
    copy_native_sources(repo, upstream)

    pro = upstream / "MSHV_WIN64.pro"
    main_h = upstream / "src/main_ms.h"
    main_cpp = upstream / "src/main_ms.cpp"
    tx_h = upstream / "src/HvTxW/hvtxw.h"
    tx_cpp = upstream / "src/HvTxW/hvtxw.cpp"

    replace_once(pro,
        "QMAKE_CXXFLAGS += -std=gnu++11 -pedantic-errors\n",
        "QMAKE_CXXFLAGS += -std=gnu++17 -pedantic-errors\n",
        "C++17 native core")
    replace_once(pro,
        "CONFIG += release warn_on exceptions_off\n",
        "CONFIG += release warn_on exceptions_off\nTARGET = DXWeaver\n",
        "DXWeaver executable target")
    replace_once(pro,
        "HEADERS = src/main_ms.h \\\n",
        "HEADERS = src/native/dxw/Domain.h \\\n src/native/dxw/CandidateScorer.h \\\n src/native/dxw/QsoStateMachine.h \\\n src/native/dxw/Ft8SlotClock.h \\\n src/native/dxw/HistoryProvider.h \\\n src/native/mshv_bridge/DxwMshvBridge.h \\\n src/native/mshv_bridge/DxwControlPanel.h \\\n src/main_ms.h \\\n",
        "native headers")
    replace_once(pro,
        "SOURCES = src/main.cpp \\\n",
        "SOURCES = src/native/dxw/CandidateScorer.cpp \\\n src/native/dxw/QsoStateMachine.cpp \\\n src/native/dxw/Ft8SlotClock.cpp \\\n src/native/mshv_bridge/DxwMshvBridge.cpp \\\n src/native/mshv_bridge/DxwControlPanel.cpp \\\n src/main.cpp \\\n",
        "native sources")

    replace_once(main_h,
        '#include "HvAggressiveW/aggressiv_d.h"\n',
        '#include "HvAggressiveW/aggressiv_d.h"\n#include "native/mshv_bridge/DxwMshvBridge.h"\n#include "native/mshv_bridge/DxwControlPanel.h"\n',
        "DXWeaver bridge includes")
    replace_once(main_h,
        "    void StopTxGlobal();\n",
        "    void StopTxGlobal();\n    void DxwHaltTx();\n    void DxwEnsureAuto();\n",
        "DXWeaver control slots")
    replace_once(main_h,
        "    QString App_Path;\n",
        "    QString App_Path;\n    dxw::DxwMshvBridge *dxwBridge = nullptr;\n    dxw::DxwControlPanel *dxwPanel = nullptr;\n",
        "DXWeaver members")

    original_autoseq = "    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)), THvTxW, SLOT(SetTextForAutoSeq(QStringList)));\n"
    native_autoseq = """    // DXWeaver 0.5: decoder -> decision engine -> native AutoSeq, all in-process.
    dxwBridge = new dxw::DxwMshvBridge("PU2BRU", this);
    dxwPanel = new dxw::DxwControlPanel(this);
    dxwPanel->setGeometry(12, 8, 760, 52);
    dxwPanel->raise();
    dxwPanel->show();
    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)), dxwBridge, SLOT(onDecode(QStringList)));
    connect(dxwBridge, SIGNAL(selectDecode(QStringList)), THvTxW, SLOT(SetTextForAutoSeq(QStringList)));
    connect(dxwBridge, SIGNAL(haltTxRequested()), this, SLOT(DxwHaltTx()));
    connect(dxwBridge, SIGNAL(ensureAutoRequested()), this, SLOT(DxwEnsureAuto()));
    connect(dxwPanel, SIGNAL(armChanged(bool)), dxwBridge, SLOT(setArmed(bool)));
    connect(dxwPanel, SIGNAL(strategyChanged(int)), dxwBridge, SLOT(setStrategy(int)));
    connect(dxwPanel, SIGNAL(haltClicked()), dxwBridge, SLOT(halt()));
    connect(dxwBridge, SIGNAL(stateChanged(QString,QString,int)), dxwPanel, SLOT(setEngineState(QString,QString,int)));
    connect(THvTxW, SIGNAL(EmitDxwLoggedQSO(QStringList)), dxwBridge, SLOT(onQsoLogged(QStringList)));
"""
    replace_once(main_cpp, original_autoseq, native_autoseq, "in-process decoder automation bridge")

    replace_once(main_cpp,
        "void Main_Ms::StopTxGlobal()\n",
        """void Main_Ms::DxwHaltTx()
{
    StopTxGlobal();
}
void Main_Ms::DxwEnsureAuto()
{
    if (!THvTxW->GetAutoIsOn())
        QMetaObject::invokeMethod(THvTxW, "auto_on", Qt::DirectConnection);
}
void Main_Ms::StopTxGlobal()
""",
        "native TX safety controls")

    replace_once(main_cpp,
        "    setWindowTitle(str_t);\n",
        "    setWindowTitle(\"DXWeaver 0.5.0\");\n",
        "DXWeaver window title")

    replace_once(tx_h,
        "    void EmitUdpConfigure(int);//2.76.7\n",
        "    void EmitUdpConfigure(int);//2.76.7\n    void EmitDxwLoggedQSO(QStringList);\n",
        "QSO logged forwarding signal")
    replace_once(tx_cpp,
        "    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), TRadioAndNetW, SLOT(SendLoggedQSO(QStringList)));\n",
        "    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), TRadioAndNetW, SLOT(SendLoggedQSO(QStringList)));\n    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), this, SIGNAL(EmitDxwLoggedQSO(QStringList)));\n",
        "QSO logged direct bridge")

    print("DXWeaver 0.5.0 native integration applied successfully")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    args = ap.parse_args()
    try:
        apply(args.upstream.resolve())
    except Exception as exc:
        print(f"DXWEAVER 0.5 PATCH FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
