#include "DxwControlPanel.h"

#include <QButtonGroup>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>

namespace dxw {

DxwControlPanel::DxwControlPanel(QWidget* parent) : QFrame(parent) {
    setObjectName("dxwHud");
    setStyleSheet(
        "QFrame#dxwHud{background:#0B0F14;border:1px solid #263341;border-radius:8px;}"
        "QLabel{color:#E6EDF3;font-family:'Segoe UI';font-weight:600;}"
        "QPushButton{background:#17212C;color:#E6EDF3;border:1px solid #324255;border-radius:5px;padding:7px 12px;font-weight:600;}"
        "QPushButton:hover{border-color:#4EA1FF;background:#1D2936;}"
        "QPushButton:checked{background:#3A301A;border-color:#E7B75B;color:#FFE1A3;}"
        "QPushButton#halt{background:#B63A3A;border-color:#E45C5C;color:white;}"
    );

    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(10, 7, 10, 7);
    layout->setSpacing(7);

    auto* brand = new QLabel("DXWEAVER 0.5.0");
    state_ = new QLabel("DISARMED");
    arm_ = new QPushButton("ARM");
    arm_->setCheckable(true);

    auto* hunt = new QPushButton("HUNT");
    auto* answer = new QPushButton("ANSWER");
    auto* both = new QPushButton("BOTH");
    hunt->setCheckable(true);
    answer->setCheckable(true);
    both->setCheckable(true);
    both->setChecked(true);
    auto* group = new QButtonGroup(this);
    group->setExclusive(true);
    group->addButton(hunt, 0);
    group->addButton(answer, 1);
    group->addButton(both, 2);

    auto* halt = new QPushButton("HALT TX");
    halt->setObjectName("halt");

    layout->addWidget(brand);
    layout->addWidget(state_);
    layout->addStretch();
    layout->addWidget(hunt);
    layout->addWidget(answer);
    layout->addWidget(both);
    layout->addWidget(arm_);
    layout->addWidget(halt);

    connect(arm_, &QPushButton::toggled, this, [this](bool checked) {
        arm_->setText(checked ? "DISARM" : "ARM");
        emit armChanged(checked);
    });
    connect(group, QOverload<int>::of(&QButtonGroup::buttonClicked), this, &DxwControlPanel::strategyChanged);
    connect(halt, &QPushButton::clicked, this, &DxwControlPanel::haltClicked);
}

void DxwControlPanel::setEngineState(QString state, QString activeCall, int candidateCount) {
    QString text = state;
    if (!activeCall.isEmpty()) text += " • " + activeCall;
    text += QString(" • %1 CAND").arg(candidateCount);
    state_->setText(text);
    if ((state == "FAULT" || state == "DISARMED") && arm_->isChecked()) arm_->setChecked(false);
}

} // namespace dxw
