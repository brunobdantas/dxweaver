#!/usr/bin/env python3
"""Apply the DXWeaver native-control extension to a pinned MSHV checkout.

The upstream MSHV tree remains external and GPL-3.0.  This script performs
small, asserted source transformations against the pinned upstream commit.  It
fails closed if upstream context changes, so CI cannot silently build a partly
patched radio application.
"""
from __future__ import annotations

import argparse
from pathlib import Path
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


def replace_all(path: Path, old: str, new: str, expected: int, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} matches in {path}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"patched {label}: {path} ({count} occurrences)")


def verify_commit(root: Path) -> None:
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception as exc:
        raise RuntimeError(f"cannot determine MSHV checkout commit: {exc}") from exc
    if actual != PINNED_UPSTREAM:
        raise RuntimeError(
            f"MSHV checkout is {actual}; DXWeaver patch is pinned to {PINNED_UPSTREAM}"
        )
    print(f"MSHV upstream verified: {actual}")


def apply(root: Path) -> None:
    verify_commit(root)

    msg_h = root / "src/HvTxW/HvRadioNetW/MessageClient.h"
    msg_cpp = root / "src/HvTxW/HvRadioNetW/MessageClient.cpp"
    net_h = root / "src/HvTxW/HvRadioNetW/radionetw.h"
    net_cpp = root / "src/HvTxW/HvRadioNetW/radionetw.cpp"
    tx_h = root / "src/HvTxW/hvtxw.h"
    tx_cpp = root / "src/HvTxW/hvtxw.cpp"
    main_h = root / "src/main_ms.h"
    main_cpp = root / "src/main_ms.cpp"
    pro = root / "MSHV_WIN64.pro"

    # Build a separate executable so stock MSHV can remain installed alongside it.
    replace_once(
        pro,
        "CONFIG += release warn_on exceptions_off\n",
        "CONFIG += release warn_on exceptions_off\nTARGET = MSHV-DXWeaver\n",
        "separate executable target",
    )

    # Status extension reports actual AUTO plus the two DXWeaver-native states.
    replace_once(
        msg_h,
        "\t\t\t\tbool,QString);\n",
        "\t\t\t\tbool,QString,bool dxw_auto_seq,bool dxw_multi_std);\n",
        "MessageClient status signature",
    )
    replace_once(
        msg_cpp,
        "                              bool tx_enabled,bool transmitting,QString tx_message)\n",
        "                              bool tx_enabled,bool transmitting,QString tx_message,bool dxw_auto_seq,bool dxw_multi_std)\n",
        "MessageClient status definition",
    )
    replace_once(
        msg_cpp,
        "        << tx_message.toUtf8();\n",
        "        << tx_message.toUtf8()\n        << true << dxw_auto_seq << dxw_multi_std; // DXWeaver native extension\n",
        "Status native acknowledgement tail",
    )

    # Configure: preserve the standard payload and optionally consume the three
    # trailing DXWeaver booleans. A marker in QStringList distinguishes an
    # actual extension from an ordinary Configure packet whose defaults are false.
    old_config_parse = """                bool generate_messages {false};
                in >> mode >> frequency_tolerance >> submode >> fast_mode >> tr_period >> rx_df
                >> dx_call >> dx_grid >> generate_messages;
"""
    new_config_parse = """                bool generate_messages {false};
                bool dxw_extension_present {false};
                bool dxw_auto_enabled {false};
                bool dxw_auto_seq {false};
                bool dxw_multi_answer_std {false};
                in >> mode >> frequency_tolerance >> submode >> fast_mode >> tr_period >> rx_df
                >> dx_call >> dx_grid >> generate_messages;
                if (!in.atEnd())
                {
                    dxw_extension_present = true;
                    in >> dxw_auto_enabled;
                    if (!in.atEnd()) in >> dxw_auto_seq;
                    if (!in.atEnd()) in >> dxw_multi_answer_std;
                }
"""
    replace_once(msg_cpp, old_config_parse, new_config_parse, "Configure extension parser")

    old_config_emit = """                    QStringList list; //mode = mode.toUpper(); submode = submode.toUpper();
                    list<<QString::fromUtf8(mode)<<QString::fromUtf8(submode);//<<QString::fromUtf8(dx_call)<<QString::fromUtf8(dx_grid);
                    Q_EMIT self_->configure(list);//,generate_messages);               
"""
    new_config_emit = """                    QStringList list; //mode = mode.toUpper(); submode = submode.toUpper();
                    list<<QString::fromUtf8(mode)<<QString::fromUtf8(submode);//<<QString::fromUtf8(dx_call)<<QString::fromUtf8(dx_grid);
                    if (dxw_extension_present)
                    {
                        list<<"DXW1"<<QString::number(dxw_auto_enabled)
                            <<QString::number(dxw_auto_seq)<<QString::number(dxw_multi_answer_std);
                    }
                    Q_EMIT self_->configure(list);//,generate_messages);               
"""
    replace_once(msg_cpp, old_config_emit, new_config_emit, "Configure extension signal payload")

    # Radio/network layer stores the requested native states so each Status packet
    # can acknowledge them to DXWeaver, and forwards the command into the UI/core.
    replace_once(
        net_h,
        "    void EmitUdpConfigure(int);//2.76.7\n",
        "    void EmitUdpConfigure(int);//2.76.7\n    void EmitDxwAutomation(bool,bool,bool); // DXWeaver: AUTO, AutoSeq, MultiAnswerStd\n",
        "RadioAndNetW native automation signal",
    )
    replace_once(
        net_h,
        "    bool s_auto;\n    bool s_tx;\n",
        "    bool s_auto;\n    bool s_tx;\n    bool s_dxw_auto_seq = false;\n    bool s_dxw_multi_std = false;\n",
        "RadioAndNetW native state members",
    )
    replace_all(
        net_cpp,
        "s_auto,s_tx,s_tx_msg);",
        "s_auto,s_tx,s_tx_msg,s_dxw_auto_seq,s_dxw_multi_std);",
        2,
        "Status native state forwarding",
    )
    old_config_tail = """    if (imode<0) return;  //qDebug()<<" OUT="<<imode<<" - "<<m<<sm;\tqDebug()<<"-----------------";
\temit EmitUdpConfigure(imode);
}
void RadioAndNetW::set_halt_tx(bool f)
"""
    new_config_tail = """    // DXWeaver extension is independent of mode changes. This intentionally
    // runs before the ordinary imode<0 early return because DXWeaver normally
    // sends Configure with an empty mode to avoid changing the operator's mode.
    if (l.count() >= 6 && l.at(2)=="DXW1")
    {
        bool dxw_auto = l.at(3).toInt();
        s_dxw_auto_seq = l.at(4).toInt();
        s_dxw_multi_std = l.at(5).toInt();
        emit EmitDxwAutomation(dxw_auto,s_dxw_auto_seq,s_dxw_multi_std);
        SendStatus(0);
    }
    if (imode<0) return;  //qDebug()<<" OUT="<<imode<<" - "<<m<<sm;\tqDebug()<<"-----------------";
\temit EmitUdpConfigure(imode);
}
void RadioAndNetW::set_halt_tx(bool f)
"""
    replace_once(net_cpp, old_config_tail, new_config_tail, "RadioAndNetW Configure native dispatch")

    # AutoSeq needs an explicit setter. Upstream SetAutoSeqMode() only selects a
    # mode/enabled appearance; it does not change the per-mode AutoSeq value.
    replace_once(
        tx_h,
        "    void SetAutoSeqMode(int,bool);\n    bool GetAutoSeq();\n",
        "    void SetAutoSeqMode(int,bool);\n    void SetAutoSeqState(bool); // DXWeaver native control\n    bool GetAutoSeq();\n",
        "HvLabAutoSeq state setter declaration",
    )
    autoseq_insert_marker = """bool HvLabAutoSeq::GetAutoSeq()
{
    return s_autoseq[s_mode];
}
"""
    autoseq_insert = """void HvLabAutoSeq::SetAutoSeqState(bool state)
{
    if (s_autoseq[s_mode] == state) return;
    s_autoseq[s_mode] = state;
    if (s_autoseq[s_mode])
    {
        if (dsty) setStyleSheet("QLabel{background-color:rgb(150,0,0);}");
        else setStyleSheet("QLabel{background-color :rgb(255,0,0);}");
    }
    else setStyleSheet("QLabel{background-color:palette(Button);}");
    emit EmitLabAutoSeqPress();
}
bool HvLabAutoSeq::GetAutoSeq()
{
    return s_autoseq[s_mode];
}
"""
    replace_once(tx_cpp, autoseq_insert_marker, autoseq_insert, "HvLabAutoSeq state setter")

    replace_once(
        tx_h,
        "    void SetAutoSeqAll(QString);\n",
        "    void SetAutoSeqAll(QString);\n    void SetDxwAutoSeq(bool);\n",
        "HvTxW native AutoSeq method declaration",
    )
    replace_once(
        tx_h,
        "    void EmitUdpConfigure(int);//2.76.7\n",
        "    void EmitUdpConfigure(int);//2.76.7\n    void EmitDxwAutomation(bool,bool,bool);\n",
        "HvTxW native signal",
    )
    replace_once(
        tx_cpp,
        "    connect(TRadioAndNetW,SIGNAL(EmitUdpConfigure(int)),this,SIGNAL(EmitUdpConfigure(int)));\n",
        "    connect(TRadioAndNetW,SIGNAL(EmitUdpConfigure(int)),this,SIGNAL(EmitUdpConfigure(int)));\n    connect(TRadioAndNetW,SIGNAL(EmitDxwAutomation(bool,bool,bool)),this,SIGNAL(EmitDxwAutomation(bool,bool,bool)));\n",
        "HvTxW native signal forwarding",
    )
    # Add the explicit per-mode AutoSeq setter before an existing stable method.
    replace_once(
        tx_cpp,
        "void HvTxW::AutoSeqLabPress()\n{\n    count_73_auto_seq = 0;// reset 73\n}\n",
        "void HvTxW::SetDxwAutoSeq(bool enabled)\n{\n    AutoSeqLab->SetAutoSeqState(enabled);\n}\nvoid HvTxW::AutoSeqLabPress()\n{\n    count_73_auto_seq = 0;// reset 73\n}\n",
        "HvTxW native AutoSeq setter",
    )

    # Main window owns the QAction-backed Multi Answer mode and the master AUTO
    # toggle. Use those existing paths so decoder/UI/core state remains coherent.
    replace_once(
        main_h,
        "    void SetUdpConfigure(int);//2.76.7\n",
        "    void SetUdpConfigure(int);//2.76.7\n    void SetDxwAutomation(bool,bool,bool);\n",
        "Main native automation slot declaration",
    )
    replace_once(
        main_cpp,
        "    connect(THvTxW, SIGNAL(EmitUdpConfigure(int)),this,SLOT(SetUdpConfigure(int)));//2.76.7\n",
        "    connect(THvTxW, SIGNAL(EmitUdpConfigure(int)),this,SLOT(SetUdpConfigure(int)));//2.76.7\n    connect(THvTxW, SIGNAL(EmitDxwAutomation(bool,bool,bool)),this,SLOT(SetDxwAutomation(bool,bool,bool)));\n",
        "Main native automation connection",
    )
    main_insert_marker = "void Main_Ms::SetMultiAnswerModStd(bool f)\n{\n"
    main_insert = """void Main_Ms::SetDxwAutomation(bool auto_enabled,bool auto_seq,bool multi_std)
{
    THvTxW->SetDxwAutoSeq(auto_seq);
    if (Multi_answer_mod_std->isChecked() != multi_std)
        Multi_answer_mod_std->setChecked(multi_std); // existing slot updates decoder + Tx widget
    if (THvTxW->GetAutoIsOn() != auto_enabled)
        THvTxW->auto_on(); // existing master AUTO path keeps TX/RX/core state coherent
}
void Main_Ms::SetMultiAnswerModStd(bool f)
{
"""
    replace_once(main_cpp, main_insert_marker, main_insert, "Main native automation implementation")

    print("DXWeaver native MSHV patch applied successfully")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="path to pinned MSHV checkout")
    args = ap.parse_args()
    root = args.root.resolve()
    if not (root / "MSHV_WIN64.pro").exists():
        raise SystemExit(f"not an MSHV checkout: {root}")
    try:
        apply(root)
    except Exception as exc:
        print(f"PATCH FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
