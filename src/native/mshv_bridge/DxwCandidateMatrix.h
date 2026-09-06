#pragma once

#include <QFrame>
#include <QStringList>

class QLabel;
class QTableWidget;

namespace dxw {

class DxwCandidateMatrix final : public QFrame {
    Q_OBJECT
public:
    explicit DxwCandidateMatrix(QWidget* parent = nullptr);

public slots:
    void setCandidateRows(QStringList rows, QString activeCall);

private:
    QTableWidget* table_{nullptr};
    QLabel* summary_{nullptr};
};

} // namespace dxw
