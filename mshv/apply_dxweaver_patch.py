#!/usr/bin/env python3
"""Apply the DXWeaver native-control extension to a pinned MSHV checkout.

The upstream MSHV tree remains external and GPL-3.0. This patcher performs
small asserted source transformations against one pinned upstream commit and
fails closed if any expected anchor changes.
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

    replace_once(
        pro,
        "CONFIG += release warn_on exceptions_off\n",
        "CONFIG += release warn_on exceptions_off\nTARGET = MSHV-DXWeaver\n",
        "separate executable target",
    )

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

    config_emit_anchor = "                    Q_EMIT self_->configure(list);//,generate_messages);"
    config_emit_replacement = """                    if (dxw_extension_present)
                    {
                        list<<"DXW1"<<QString::number(dxw_auto_enabled)
                            <<QString::number(dxw_auto_seq)<<QString::number(dxw_multi_answer_std);
                    }
                    Q_EMIT self_->configure(list);//,generate_messages);"""
    replace_once(msg_cpp, config_emit_anchor, config_emit_replacement, "Configure extension signal payload")

    replace_once(
        net_h,
        "    void SendOtpCheck(QString s);\n",
        "    void SendOtpCheck(QString s);\n    void SetDxwActualState(bool,bool,bool); // actual AUTO, AutoSeq, MultiAnswerStd\n",
        "RadioAndNetW actual-state method declaration",
    )
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
    new_config_tail = """    // DXWeaver extension is independent of mode changes. Run it before the
    // ordinary imode<0 return because the controller normally sends empty mode.
    // Do NOT acknowledge the requested values here. Main_Ms applies them first
    // and calls SetDxwActualState() with the values read back from MSHV.
    if (l.count() >= 6 && l.at(2)=="DXW1")
    {
        bool dxw_auto = l.at(3).toInt();
        bool dxw_auto_seq = l.at(4).toInt();
        bool dxw_multi_std = l.at(5).toInt();
        emit EmitDxwAutomation(dxw_auto,dxw_auto_seq,dxw_multi_std);
    }
    if (imode<0) return;  //qDebug()<<" OUT="<<imode<<" - "<<m<<sm;\tqDebug()<<"-----------------";
\temit EmitUdpConfigure(imode);
}
void RadioAndNetW::SetDxwActualState(bool auto_enabled,bool auto_seq,bool multi_std)
{
    // These are actual values read back after Main_Ms has applied the request.
    s_auto = auto_enabled;
    s_dxw_auto_seq = auto_seq;
    s_dxw_multi_std = multi_std;
    SendStatus(0);
}
void RadioAndNetW::set_halt_tx(bool f)
"""
    replace_once(net_cpp, old_config_tail, new_config_tail, "RadioAndNetW actual-state acknowledgement")

    replace_once(
        tx_h,
        "    void SetAutoSeqMode(int,bool);\n    bool GetAutoSeq();\n",
        "    void SetAutoSeqMode(int,bool);\n    void SetAutoSeqState(bool); // DXWeaver native control\n    bool GetAutoSeq();\n",
        "HvLabAutoSeq state setter declaration",
    )
    autoseq_get_anchor = "bool HvLabAutoSeq::GetAutoSeq()\n"
    autoseq_method = """void HvLabAutoSeq::SetAutoSeqState(bool state)
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
"""
    replace_once(tx_cpp, autoseq_get_anchor, autoseq_method, "HvLabAutoSeq state setter")

    hvtxw_autoseq_anchor = """    void SetAutoSeqAll(QString);

    QString GetDirectLogQso()
"""
    hvtxw_autoseq_replacement = """    void SetAutoSeqAll(QString);
    void SetDxwAutoSeq(bool);
    bool GetDxwAutoSeq() { return AutoSeqLab->GetAutoSeq(); }
    void SetDxwActualState(bool,bool,bool);

    QString GetDirectLogQso()
"""
    replace_once(
        tx_h,
        hvtxw_autoseq_anchor,
        hvtxw_autoseq_replacement,
        "HvTxW native AutoSeq/actual-state methods",
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
    autoseq_press_anchor = "void HvTxW::AutoSeqLabPress()\n"
    autoseq_press_replacement = """void HvTxW::SetDxwAutoSeq(bool enabled)
{
    AutoSeqLab->SetAutoSeqState(enabled);
}
void HvTxW::SetDxwActualState(bool auto_enabled,bool auto_seq,bool multi_std)
{
    TRadioAndNetW->SetDxwActualState(auto_enabled,auto_seq,multi_std);
}
void HvTxW::AutoSeqLabPress()
"""
    replace_once(tx_cpp, autoseq_press_anchor, autoseq_press_replacement, "HvTxW native AutoSeq/actual-state bridge")

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
    main_std_anchor = "void Main_Ms::SetMultiAnswerModStd(bool f)\n"
    main_std_replacement = """void Main_Ms::SetDxwAutomation(bool auto_enabled,bool auto_seq,bool multi_std)
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
void Main_Ms::SetMultiAnswerModStd(bool f)
"""
    replace_once(main_cpp, main_std_anchor, main_std_replacement, "Main native actual-state implementation")

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
