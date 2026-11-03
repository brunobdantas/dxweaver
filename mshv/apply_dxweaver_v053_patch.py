#!/usr/bin/env python3
"""Build-time integration patch for MSHV Enhanced.

The upstream MSHV tree is never edited in this repository. CI downloads the
exact pinned upstream revision, copies the Enhanced controller into that
working tree and applies a small, fail-closed integration patch.

Any upstream drift makes the patch fail instead of silently changing RF
behaviour.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

PINNED_UPSTREAM = "50ea1a7b5bf20c688ccc72107e389f06673deac6"
VERSION = "0.1.1"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {label}: {path}")


def replace_count(path: Path, old: str, new: str, expected: int, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} matches in {path}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"patched {label}: {path} ({count} matches)")


def require_once(path: Path, needle: str, label: str) -> None:
    count = path.read_text(encoding="utf-8").count(needle)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    print(f"verified {label}: {path}")


def verify_commit(root: Path) -> None:
    marker = root / ".mshv-enhanced-upstream-revision"
    legacy_marker = root / ".dxweaver-upstream-revision"
    if marker.is_file():
        actual = marker.read_text(encoding="utf-8").strip()
    elif legacy_marker.is_file():
        actual = legacy_marker.read_text(encoding="utf-8").strip()
    elif (root / ".git").exists():
        actual = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    else:
        raise RuntimeError("cannot verify MSHV revision: no git metadata or revision marker")

    if actual != PINNED_UPSTREAM:
        raise RuntimeError(f"unexpected MSHV commit {actual}; expected {PINNED_UPSTREAM}")
    print(f"verified upstream revision: {actual}")


def refresh_to_pinned_upstream(root: Path) -> None:
    """Replace the workflow's legacy MSHV snapshot with the pinned 2.76.8 rc008 tree.

    Preserve the local .git directory because the outer CI uses it to export
    the corresponding GPL source/diff after the build.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        archive = td_path / "mshv.zip"
        url = f"https://github.com/LZ2HV/MSHV/archive/{PINNED_UPSTREAM}.zip"
        print(f"downloading pinned upstream {PINNED_UPSTREAM}")
        urllib.request.urlretrieve(url, archive)
        extract = td_path / "extract"
        extract.mkdir()
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract)
        roots = [x for x in extract.iterdir() if x.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"unexpected upstream archive layout: {roots}")
        src_root = roots[0]

        for child in list(root.iterdir()):
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in src_root.iterdir():
            dst = root / child.name
            if child.is_dir():
                shutil.copytree(child, dst)
            else:
                shutil.copy2(child, dst)

        (root / ".dxweaver-upstream-revision").write_text(PINNED_UPSTREAM, encoding="utf-8")
        print("refreshed working tree to pinned MSHV 2.76.8 rc008")


def copy_enhanced_sources(repo: Path, upstream: Path) -> None:
    src = repo / "src" / "native" / "mshv_bridge"
    if not (src / "MshvEnhancedController.h").is_file():
        raise RuntimeError("missing src/enhanced/MshvEnhancedController.h")
    if not (src / "MshvEnhancedController.cpp").is_file():
        raise RuntimeError("missing src/enhanced/MshvEnhancedController.cpp")

    dst = upstream / "src" / "enhanced"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "MshvEnhancedController.h", dst / "MshvEnhancedController.h")
    shutil.copy2(src / "MshvEnhancedController.cpp", dst / "MshvEnhancedController.cpp")
    print(f"copied Enhanced sources to {dst}")


def apply(upstream: Path) -> None:
    refresh_to_pinned_upstream(upstream)
    verify_commit(upstream)
    repo = Path(__file__).resolve().parents[1]
    copy_enhanced_sources(repo, upstream)

    pro = upstream / "MSHV_WIN64.pro"
    main_h = upstream / "src/main_ms.h"
    main_cpp = upstream / "src/main_ms.cpp"
    tx_h = upstream / "src/HvTxW/hvtxw.h"
    tx_cpp = upstream / "src/HvTxW/hvtxw.cpp"
    log_h = upstream / "src/HvTxW/HvLogW/hvlogw.h"
    log_cpp = upstream / "src/HvTxW/HvLogW/hvlogw.cpp"

    require_once(pro, "QMAKE_CXXFLAGS += -std=gnu++11 -pedantic-errors\n", "gnu++11 dialect")

    replace_once(
        pro,
        "CONFIG += release warn_on console exceptions_off\n",
        "CONFIG += release warn_on console exceptions_off\nTARGET = DXWeaver\n",
        "Enhanced executable target",
    )
    replace_once(
        pro,
        "HEADERS = src/main_ms.h \\\n",
        "HEADERS = src/enhanced/MshvEnhancedController.h \\\n src/main_ms.h \\\n",
        "Enhanced header in qmake project",
    )
    replace_once(
        pro,
        "SOURCES = src/main.cpp \\\n",
        "SOURCES = src/enhanced/MshvEnhancedController.cpp \\\n src/main.cpp \\\n",
        "Enhanced source in qmake project",
    )

    replace_once(
        main_h,
        '#include "HvAggressiveW/aggressiv_d.h"\n',
        '#include "HvAggressiveW/aggressiv_d.h"\n'
        '#include "enhanced/MshvEnhancedController.h"\n',
        "Enhanced controller include",
    )
    replace_once(
        main_h,
        "    void StopTxGlobal();\n",
        "    void StopTxGlobal();\n"
        "    void EnhancedHaltTx();\n"
        "    void EnhancedEnsureAuto();\n",
        "Enhanced control slots",
    )
    replace_once(
        main_h,
        "    QString App_Path;\n",
        "    QString App_Path;\n"
        "    MshvEnhancedController *enhancedController = nullptr;\n",
        "Enhanced controller member",
    )

    original_autoseq = (
        "    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)), "
        "THvTxW, SLOT(SetTextForAutoSeq(QStringList)));\n"
    )
    enhanced_autoseq = """    // MSHV Enhanced: AutoQSO observes every decode and always forwards it
    // to the native MSHV AutoSeq state machine.
    enhancedController = new MshvEnhancedController(App_Path, this);
    enhancedController->setStationIdentity(THvTxW->EnhancedStationCall(), THvTxW->EnhancedStationGrid());
    enhancedController->setBand(THvTxW->EnhancedBand());
    enhancedController->setModeId(THvTxW->EnhancedModeId());

    connect(TDecodeList1, SIGNAL(EmitRxTextForAutoSeq(QStringList)),
            enhancedController, SLOT(onDecode(QStringList)));
    connect(enhancedController, SIGNAL(selectAutoDecode(QStringList)),
            THvTxW, SLOT(SetTextForAutoSeq(QStringList)));
    connect(enhancedController, SIGNAL(selectHuntDecode(QString,QString,QString,QString,QString)),
            THvTxW, SLOT(DecListTextAll(QString,QString,QString,QString,QString)));
    connect(enhancedController, SIGNAL(ensureAutoRequested()),
            this, SLOT(EnhancedEnsureAuto()));
    connect(enhancedController, SIGNAL(requestCq()),
            THvTxW, SLOT(ResetQSO()));
    connect(enhancedController, SIGNAL(haltTxRequested()),
            this, SLOT(EnhancedHaltTx()));
    connect(enhancedController, SIGNAL(skipTx1Changed(bool)),
            THvTxW, SLOT(SetStartFromTx2Tx1(bool)));

    connect(THvTxW, SIGNAL(EmitEnhancedIdentity(QString,QString)),
            enhancedController, SLOT(setStationIdentity(QString,QString)));
    connect(THvTxW, SIGNAL(EmitEnhancedBand(QString)),
            enhancedController, SLOT(setBand(QString)));
    connect(THvTxW, SIGNAL(EmitEnhancedMode(int)),
            enhancedController, SLOT(setModeId(int)));
    connect(THvTxW, SIGNAL(EmitEnhancedAdif(QString)),
            enhancedController, SLOT(onAdifRecord(QString)));
    connect(THvTxW, SIGNAL(EmitQSOProgress(int)),
            enhancedController, SLOT(onQsoProgress(int)));

    // A manual double-click/CALL remains a native MSHV action; Enhanced only
    // records the override so it does not immediately select another target.
    connect(TDecodeList1, SIGNAL(ListSelectedTextAll(QString,QString,QString,QString,QString)),
            enhancedController, SLOT(onManualTarget(QString,QString,QString,QString,QString)));
"""
    replace_once(main_cpp, original_autoseq, enhanced_autoseq, "decoder/AutoSeq bridge")

    replace_once(
        main_cpp,
        "    V_l->addWidget(THvTxW);\n",
        "    V_l->addWidget(THvTxW);\n"
        "    V_l->insertWidget(0, enhancedController);\n",
        "Enhanced command bar layout",
    )

    replace_once(
        main_cpp,
        "void Main_Ms::StopTxGlobal()\n",
        """void Main_Ms::EnhancedHaltTx()
{
    StopTxGlobal();
}
void Main_Ms::EnhancedEnsureAuto()
{
    if (!THvTxW->GetAutoIsOn())
        THvTxW->auto_on();
}
void Main_Ms::StopTxGlobal()
""",
        "Enhanced TX control slots",
    )

    replace_once(
        main_cpp,
        "    setWindowTitle(str_t);\n",
        '    setWindowTitle(QString("MSHV Enhanced 0.1.1 - ")+str_t);\n',
        "Enhanced window title",
    )

    # HvTxW exposes only the station state needed by the controller. The
    # actual message generation/AutoSeq implementation remains upstream MSHV.
    replace_once(
        tx_h,
        "    void RefreshOtpKeyMsg();//2.76 \n",
        "    void RefreshOtpKeyMsg();//2.76 \n"
        "    QString EnhancedStationCall() const { return list_macros.value(0); }\n"
        "    QString EnhancedStationGrid() const { return list_macros.value(1); }\n"
        "    QString EnhancedBand() const { return s_band; }\n"
        "    int EnhancedModeId() const { return s_mode; }\n",
        "Enhanced station getters",
    )

    replace_once(
        tx_h,
        "    void EmitUdpConfigure(int);//2.76.7\n",
        "    void EmitUdpConfigure(int);//2.76.7\n"
        "    void EmitEnhancedIdentity(QString,QString);\n"
        "    void EmitEnhancedBand(QString);\n"
        "    void EmitEnhancedMode(int);\n"
        "    void EmitEnhancedAdif(QString);\n",
        "Enhanced station/log signals",
    )

    replace_once(
        tx_cpp,
        "    connect(THvLogW, SIGNAL(EmitAdifRecord(QString)), TRadioAndNetW, SLOT(SendAdifRecord(QString)));\n",
        "    connect(THvLogW, SIGNAL(EmitAdifRecord(QString)), TRadioAndNetW, SLOT(SendAdifRecord(QString)));\n"
        "    connect(THvLogW, SIGNAL(EmitEnhancedAdif(QString)), this, SIGNAL(EmitEnhancedAdif(QString)));\n",
        "unconditional Enhanced ADIF bridge",
    )

    replace_once(
        tx_cpp,
        "    list_macros = list;\n    s_my_base_call = MultiAnswerMod->FindBaseFullCallRemAllSlash(list_macros.at(0));\n",
        "    list_macros = list;\n"
        "    emit EmitEnhancedIdentity(list_macros.value(0), list_macros.value(1));\n"
        "    s_my_base_call = MultiAnswerMod->FindBaseFullCallRemAllSlash(list_macros.at(0));\n",
        "identity update signal",
    )

    replace_once(
        tx_cpp,
        "    s_band = s;\n    if (s_mode==11 || s_mode==13 || s_mode==18 || allq65) fpsk_restrict = true;",
        "    s_band = s;\n"
        "    emit EmitEnhancedBand(s_band);\n"
        "    if (s_mode==11 || s_mode==13 || s_mode==18 || allq65) fpsk_restrict = true;",
        "band update signal",
    )

    replace_once(
        tx_cpp,
        "void HvTxW::ModeChanget(int mode,bool f)\n{\n",
        "void HvTxW::ModeChanget(int mode,bool f)\n{\n"
        "    emit EmitEnhancedMode(mode);\n",
        "mode update signal",
    )

    replace_once(
        log_h,
        "   void EmitAdifRecord(QString);\n",
        "   void EmitAdifRecord(QString);\n"
        "   void EmitEnhancedAdif(QString);\n",
        "unconditional Enhanced ADIF signal",
    )

    normal_adif_emit = "        if (s_udportcp_broad_logged_adif) emit EmitAdifRecord(MakeAdifString(rowt));\n"
    replace_once(
        log_cpp,
        normal_adif_emit,
        normal_adif_emit + "        emit EmitEnhancedAdif(MakeAdifString(rowt));\n",
        "unconditional ADIF on completed QSO",
    )

    manual_adif_emit = (
        "    if (s_udportcp_broad_logged_adif) emit EmitAdifRecord(MakeAdifString(rowt));\n"
        "\n"
        "    if (s_allowed_modes && (f_isCheck[0] || f_isCheck[3])) GetMarkTextAllFromLog_p(s_band,s_mode);\n"
    )
    replace_once(
        log_cpp,
        manual_adif_emit,
        "    if (s_udportcp_broad_logged_adif) emit EmitAdifRecord(MakeAdifString(rowt));\n"
        "    emit EmitEnhancedAdif(MakeAdifString(rowt));\n"
        "\n"
        "    if (s_allowed_modes && (f_isCheck[0] || f_isCheck[3])) GetMarkTextAllFromLog_p(s_band,s_mode);\n",
        "unconditional ADIF on manual QSO",
    )

    require_once(main_cpp, "    V_l->insertWidget(0, enhancedController);\n", "Enhanced panel layout")
    require_once(main_cpp, "            enhancedController, SLOT(onDecode(QStringList)));\n", "Enhanced decode observer")
    require_once(tx_h, "    void EmitEnhancedAdif(QString);\n", "Enhanced ADIF bridge signal")
    require_once(log_h, "   void EmitEnhancedAdif(QString);\n", "Enhanced logger signal")

    print(f"MSHV Enhanced {VERSION} integration applied successfully")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()

    try:
        apply(args.upstream.resolve())
    except Exception as exc:
        print(f"MSHV ENHANCED {VERSION} PATCH FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
