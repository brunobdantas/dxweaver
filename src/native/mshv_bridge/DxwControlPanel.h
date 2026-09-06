#pragma once

#include <QFrame>
#include <QString>

class QLabel;
class QPushButton;

namespace dxw {

class DxwControlPanel final : public QFrame {
    Q_OBJECT
public:
    explicit DxwControlPanel(QWidget* parent = nullptr);

    // Applies the DXWeaver application-wide stylesheet. The external QSS is
    // preferred so designers can audit the shipped design system; a compact
    // embedded fallback keeps the cockpit dark if the resource is unavailable.
    static bool applyGlobalTheme(const QString& appPath);

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
