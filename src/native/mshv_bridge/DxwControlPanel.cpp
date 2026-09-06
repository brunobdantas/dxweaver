#include "DxwControlPanel.h"

#include <QApplication>
#include <QButtonGroup>
#include <QDir>
#include <QFile>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QSizePolicy>
#include <QStyle>

namespace dxw {

bool DxwControlPanel::applyGlobalTheme(const QString& appPath) {
    const QString qssPath = QDir(appPath).filePath("settings/resources/dxweaver/DxTheme.qss");
    QFile qss(qssPath);
    if (qss.open(QIODevice::ReadOnly | QIODevice::Text)) {
        qApp->setStyleSheet(QString::fromUtf8(qss.readAll()));
        return true;
    }

    // Fail visibly dark rather than silently falling back to the classic light
    // MSHV palette when the external design-system file is missing.
    qApp->setStyleSheet(
        "QWidget{background:#0B0F14;color:#E6EDF3;}"
        "QFrame{background:#111821;border-color:#263341;}"
        "QPushButton{background:#162536;color:#E6EDF3;border:1px solid #263341;padding:5px 10px;}"
        "QLineEdit,QComboBox,QSpinBox,QTableView,QTableWidget,QTextEdit,QPlainTextEdit{"
        "background:#0D141C;color:#E6EDF3;border:1px solid #263341;}"
        "QHeaderView::section{background:#111821;color:#9FB0C0;border:0;border-bottom:1px solid #263341;}"
    );
    return false;
}

DxwControlPanel::DxwControlPanel(QWidget* parent) : QFrame(parent) {
    setObjectName("dxwHud");
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setMinimumHeight(44);
    setMaximumHeight(56);

    QHBoxLayout* layout = new QHBoxLayout(this);
    layout->setContentsMargins(10, 5, 10, 5);
    layout->setSpacing(7);

    QLabel* brand = new QLabel("DXWEAVER 0.5.1", this);
    brand->setObjectName("dxwBrand");
    state_ = new QLabel("DISARMED", this);
    state_->setObjectName("dxwState");

    arm_ = new QPushButton("ARM", this);
    arm_->setObjectName("dxwArm");
    arm_->setCheckable(true);

    QPushButton* hunt = new QPushButton("HUNT", this);
    QPushButton* answer = new QPushButton("ANSWER", this);
    QPushButton* both = new QPushButton("BOTH", this);
    hunt->setProperty("dxwStrategy", true);
    answer->setProperty("dxwStrategy", true);
    both->setProperty("dxwStrategy", true);
    hunt->setCheckable(true);
    answer->setCheckable(true);
    both->setCheckable(true);
    both->setChecked(true);

    QButtonGroup* group = new QButtonGroup(this);
    group->setExclusive(true);
    group->addButton(hunt, 0);
    group->addButton(answer, 1);
    group->addButton(both, 2);

    QPushButton* halt = new QPushButton("HALT TX", this);
    halt->setObjectName("dxwHalt");

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
    if (!activeCall.isEmpty()) text += "  |  " + activeCall;
    text += QString("  |  %1 CAND").arg(candidateCount);
    state_->setText(text);
    state_->setProperty("fault", state == "FAULT");
    state_->style()->unpolish(state_);
    state_->style()->polish(state_);
    if ((state == "FAULT" || state == "DISARMED") && arm_->isChecked()) arm_->setChecked(false);
}

} // namespace dxw
