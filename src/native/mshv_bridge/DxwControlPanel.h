#pragma once

#include <QFrame>

class QLabel;
class QPushButton;

namespace dxw {

class DxwControlPanel final : public QFrame {
    Q_OBJECT
public:
    explicit DxwControlPanel(QWidget* parent = nullptr);

signals:
    void armChanged(bool armed);
    void strategyChanged(int strategy);
    void haltClicked();

public slots:
    void setEngineState(QString state, QString activeCall, int candidateCount);

private:
    QPushButton* arm_{nullptr};
    QLabel* state_{nullptr};
};

} // namespace dxw
