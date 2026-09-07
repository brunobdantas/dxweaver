#!/usr/bin/env python3
"""Fail-closed build-time integration patch for DXWeaver 0.5.3.

The official MSHV source remains the GPL-3.0 radio/DSP foundation. DXWeaver's
C++11-compatible in-process automation and intelligence modules are injected
without changing the legacy compiler dialect. The v0.5.3 patch keeps the
native HUNT/ANSWER routing and adds a fail-safe HUNT liveness watchdog so an
unanswered/stale target cannot remain selected indefinitely.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

PINNED_UPSTREAM = "8f93eb3e25056f0cb18699ef6c3bef3998c52cdf"
VERSION = "0.5.3"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {label}: {path}")


def require_once(path: Path, text: str, label: str) -> None:
    count = path.read_text(encoding="utf-8").count(text)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    print(f"verified {label}: {path}")


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

    theme_src = repo / "src/native/mshv_bridge/DxTheme.qss"
    if not theme_src.is_file():
        raise RuntimeError(f"DXWeaver theme missing: {theme_src}")
    theme_dst = upstream / "bin/settings/resources/dxweaver/DxTheme.qss"
    theme_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(theme_src, theme_dst)
    print(f"copied DXWeaver design system: {theme_dst}")


def apply(upstream: Path) -> None:
    verify_commit(upstream)
    repo = Path(__file__).resolve().parents[1]
    copy_native_sources(repo, upstream)

    pro = upstream / "MSHV_WIN64.pro"
    main_h = upstream / "src/main_ms.h"
    main_cpp = upstream / "src/main_ms.cpp"
    tx_h = upstream / "src/HvTxW/hvtxw.h"
    tx_cpp = upstream / "src/HvTxW/hvtxw.cpp"

    require_once(pro, "QMAKE_CXXFLAGS += -std=gnu++11 -pedantic-errors\n", "legacy gnu++11 dialect")
    if "-std=gnu++17" in pro.read_text(encoding="utf-8"):
        raise RuntimeError("MSHV project unexpectedly requests gnu++17")

    replace_once(
        pro,
        "QT += widgets axcontainer network websockets\n",
        "QT += widgets axcontainer network websockets sql\n",
        "QtSql read-only history support",
    )
    replace_once(
        pro,
        "CONFIG += release warn_on exceptions_off\n",
        "CONFIG += release warn_on exceptions_off\nTARGET = DXWeaver\n",
        "DXWeaver executable target",
    )
    replace_once(
        pro,
        "HEADERS = src/main_ms.h \\\n",
        "HEADERS = src/native/dxw/Domain.h \\\n src/native/dxw/CandidateScorer.h \\\n src/native/dxw/CtyResolver.h \\\n src/native/dxw/Ft8SlotClock.h \\\n src/native/dxw/HistoryIndex.h \\\n src/native/dxw/HistoryProvider.h \\\n src/native/dxw/HuntWatchdog.h \\\n src/native/dxw/QsoStateMachine.h \\\n src/native/mshv_bridge/DxwHistoryCache.h \\\n src/native/mshv_bridge/DxwMshvBridge.h \\\n src/native/mshv_bridge/DxwControlPanel.h \\\n src/native/mshv_bridge/DxwCandidateMatrix.h \\\n src/main_ms.h \\\n",
        "native headers",
    )
    replace_once(
        pro,
        "SOURCES = src/main.cpp \\\n",
        "SOURCES = src/native/dxw/CandidateScorer.cpp \\\n src/native/dxw/CtyResolver.cpp \\\n src/native/dxw/Ft8SlotClock.cpp \\\n src/native/dxw/HistoryIndex.cpp \\\n src/native/dxw/HuntWatchdog.cpp \\\n src/native/dxw/QsoStateMachine.cpp \\\n src/native/mshv_bridge/DxwHistoryCache.cpp \\\n src/native/mshv_bridge/DxwMshvBridge.cpp \\\n src/native/mshv_bridge/DxwControlPanel.cpp \\\n src/native/mshv_bridge/DxwCandidateMatrix.cpp \\\n src/main.cpp \\\n",
        "native sources",
    )

    replace_once(
        main_h,
        '#include "HvAggressiveW/aggressiv_d.h"\n',
        '#include "HvAggressiveW/aggressiv_d.h"\n'
        '#include "native/mshv_bridge/DxwMshvBridge.h"\n'
        '#include "native/mshv_bridge/DxwControlPanel.h"\n'
        '#include "native/mshv_bridge/DxwCandidateMatrix.h"\n',
        "DXWeaver bridge includes",
    )
    replace_once(
        main_h,
        "    void StopTxGlobal();\n",
        "    void StopTxGlobal();\n    void DxwHaltTx();\n    void DxwEnsureAuto();\n",
        "DXWeaver control slots",
    )
    replace_once(
        main_h,
        "    QString App_Path;\n",
        "    QString App_Path;\n"
        "    dxw::DxwMshvBridge *dxwBridge = nullptr;\n"
        "    dxw::DxwControlPanel *dxwPanel = nullptr;\n"
        "    dxw::DxwCandidateMatrix *dxwCandidates = nullptr;\n",
        "DXWeaver members",
    )

    original_autoseq = (
        "    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)), "
        "THvTxW, SLOT(SetTextForAutoSeq(QStringList)));\n"
    )
    native_autoseq = """    // DXWeaver 0.5.3: decoder -> intelligence -> native selection/AutoSeq, entirely in-process.
    dxw::DxwControlPanel::applyGlobalTheme(App_Path);
    dxwBridge = new dxw::DxwMshvBridge(THvTxW->DxwStationCall(), THvTxW->DxwStationGrid(),
                                       THvTxW->DxwBand(), App_Path, this);
    dxwPanel = new dxw::DxwControlPanel(this);
    dxwCandidates = new dxw::DxwCandidateMatrix(this);
    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)), dxwBridge, SLOT(onDecode(QStringList)));
    connect(dxwBridge, SIGNAL(selectHuntDecode(QString,QString,QString,QString,QString)),
            THvTxW, SLOT(DecListTextAll(QString,QString,QString,QString,QString)));
    connect(dxwBridge, SIGNAL(selectDecode(QStringList)), THvTxW, SLOT(SetTextForAutoSeq(QStringList)));
    connect(dxwBridge, SIGNAL(haltTxRequested()), this, SLOT(DxwHaltTx()));
    connect(dxwBridge, SIGNAL(ensureAutoRequested()), this, SLOT(DxwEnsureAuto()));
    connect(dxwPanel, SIGNAL(armChanged(bool)), dxwBridge, SLOT(setArmed(bool)));
    connect(dxwPanel, SIGNAL(strategyChanged(int)), dxwBridge, SLOT(setStrategy(int)));
    connect(dxwPanel, SIGNAL(haltClicked()), dxwBridge, SLOT(halt()));
    connect(dxwBridge, SIGNAL(stateChanged(QString,QString,int)), dxwPanel, SLOT(setEngineState(QString,QString,int)));
    connect(dxwBridge, SIGNAL(candidateMatrixChanged(QStringList,QString)), dxwCandidates, SLOT(setCandidateRows(QStringList,QString)));
    connect(THvTxW, SIGNAL(EmitDxwLoggedQSO(QStringList)), dxwBridge, SLOT(onQsoLogged(QStringList)));
    connect(THvTxW, SIGNAL(EmitDxwStationIdentity(QString,QString)), dxwBridge, SLOT(setStationIdentity(QString,QString)));
    connect(THvTxW, SIGNAL(EmitDxwBand(QString)), dxwBridge, SLOT(setBand(QString)));
"""
    replace_once(main_cpp, original_autoseq, native_autoseq, "in-process decoder automation bridge")

    replace_once(
        main_cpp,
        "    dsty = false;\n    if (styid==1) dsty = true;\n",
        "    dsty = true; // DXWeaver owns a single dark visual identity.\n",
        "force upstream dark widget palette",
    )
    replace_once(main_cpp, "    V_l->setSpacing(0);\n", "    V_l->setSpacing(2);\n", "master layout spacing")
    replace_once(
        main_cpp,
        "    V_l->addWidget(THvTxW);\n",
        "    V_l->addWidget(THvTxW);\n"
        "    V_l->insertWidget(0, dxwPanel);\n"
        "    V_l->insertWidget(1, dxwCandidates);\n",
        "DXWeaver cockpit layout ownership",
    )
    replace_once(
        main_cpp,
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
        "native TX safety controls",
    )
    replace_once(main_cpp, "    setWindowTitle(str_t);\n", '    setWindowTitle("DXWeaver 0.5.3");\n', "DXWeaver window title")

    replace_once(
        tx_h,
        "    void RefreshOtpKeyMsg();//2.76    \n\npublic slots:\n",
        """    void RefreshOtpKeyMsg();//2.76    
    QString DxwStationCall() const { return list_macros.value(0); }
    QString DxwStationGrid() const { return list_macros.value(1); }
    QString DxwBand() const { return s_band; }

public slots:
""",
        "station identity getters",
    )
    replace_once(
        tx_h,
        "    void EmitUdpConfigure(int);//2.76.7\n",
        "    void EmitUdpConfigure(int);//2.76.7\n"
        "    void EmitDxwLoggedQSO(QStringList);\n"
        "    void EmitDxwStationIdentity(QString,QString);\n"
        "    void EmitDxwBand(QString);\n",
        "DXWeaver native state signals",
    )
    replace_once(
        tx_cpp,
        "    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), TRadioAndNetW, SLOT(SendLoggedQSO(QStringList)));\n",
        "    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), TRadioAndNetW, SLOT(SendLoggedQSO(QStringList)));\n"
        "    connect(THvLogW, SIGNAL(EmitLoggedQSO(QStringList)), this, SIGNAL(EmitDxwLoggedQSO(QStringList)));\n",
        "QSO logged direct bridge",
    )
    replace_once(
        tx_cpp,
        "    list_macros = list;\n    s_my_base_call = MultiAnswerMod->FindBaseFullCallRemAllSlash(list_macros.at(0));\n",
        "    list_macros = list;\n"
        "    emit EmitDxwStationIdentity(list_macros.value(0), list_macros.value(1));\n"
        "    s_my_base_call = MultiAnswerMod->FindBaseFullCallRemAllSlash(list_macros.at(0));\n",
        "dynamic callsign/grid signal",
    )
    replace_once(
        tx_cpp,
        "    s_band = s;\n    if (s_mode==11 || s_mode==13 || s_mode==18 || allq65) fpsk_restrict = true;",
        "    s_band = s;\n"
        "    emit EmitDxwBand(s_band);\n"
        "    if (s_mode==11 || s_mode==13 || s_mode==18 || allq65) fpsk_restrict = true;",
        "dynamic band signal",
    )

    patched_main = main_cpp.read_text(encoding="utf-8")
    if "dxwPanel->setGeometry" in patched_main or "dxwPanel->raise" in patched_main:
        raise RuntimeError("absolute DXWeaver panel geometry/z-order leaked into patched main window")
    require_once(main_cpp, "    V_l->insertWidget(0, dxwPanel);\n", "DXWeaver panel layout position")
    require_once(main_cpp, "    V_l->insertWidget(1, dxwCandidates);\n", "candidate matrix layout position")
    require_once(
        main_cpp,
        "    connect(dxwBridge, SIGNAL(selectHuntDecode(QString,QString,QString,QString,QString)),\n"
        "            THvTxW, SLOT(DecListTextAll(QString,QString,QString,QString,QString)));\n",
        "HUNT native decode-click route",
    )
    require_once(
        main_cpp,
        "    connect(dxwBridge, SIGNAL(selectDecode(QStringList)), THvTxW, SLOT(SetTextForAutoSeq(QStringList)));\n",
        "ANSWER native AutoSeq route",
    )

    bridge = upstream / "src/native/mshv_bridge/DxwMshvBridge.cpp"
    require_once(bridge, "huntWatchdog_.shouldExpire", "HUNT watchdog expiry integration")
    require_once(bridge, "std::vector<Candidate> DxwMshvBridge::freshHuntPool", "fresh CQ-only HUNT pool")

    print(f"DXWeaver {VERSION} native integration applied successfully")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    args = ap.parse_args()
    try:
        apply(args.upstream.resolve())
    except Exception as exc:
        print(f"DXWEAVER {VERSION} PATCH FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
