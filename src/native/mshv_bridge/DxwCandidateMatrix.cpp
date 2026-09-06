#include "DxwCandidateMatrix.h"

#include <QAbstractItemView>
#include <QBrush>
#include <QColor>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QLabel>
#include <QSizePolicy>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVBoxLayout>
#include <algorithm>

namespace dxw {

DxwCandidateMatrix::DxwCandidateMatrix(QWidget* parent) : QFrame(parent) {
    setObjectName("dxwCandidateMatrix");
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setMinimumHeight(132);
    setMaximumHeight(176);

    QVBoxLayout* root = new QVBoxLayout(this);
    root->setContentsMargins(8, 5, 8, 7);
    root->setSpacing(4);

    QHBoxLayout* titleRow = new QHBoxLayout();
    titleRow->setContentsMargins(0, 0, 0, 0);
    QLabel* title = new QLabel("CANDIDATES MATRIX", this);
    title->setObjectName("dxwMatrixTitle");
    summary_ = new QLabel("0 ranked | live scorer", this);
    summary_->setObjectName("dxwMatrixSummary");
    titleRow->addWidget(title);
    titleRow->addStretch();
    titleRow->addWidget(summary_);
    root->addLayout(titleRow);

    table_ = new QTableWidget(0, 13, this);
    table_->setObjectName("dxwCandidatesTable");
    table_->setHorizontalHeaderLabels(QStringList()
        << "CALL" << "SCORE" << "DXCC" << "BAND" << "MODE" << "SLOT"
        << "SNR" << "ENTITY" << "CQ/ITU" << "KM" << "AZ" << "HISTORY" << "TARGET");
    table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setSelectionMode(QAbstractItemView::SingleSelection);
    table_->setAlternatingRowColors(true);
    table_->setShowGrid(false);
    table_->verticalHeader()->setVisible(false);
    table_->verticalHeader()->setDefaultSectionSize(22);
    table_->horizontalHeader()->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    table_->horizontalHeader()->setStretchLastSection(false);
    table_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    table_->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);

    for (int c = 0; c < table_->columnCount(); ++c)
        table_->horizontalHeader()->setSectionResizeMode(c, QHeaderView::ResizeToContents);
    table_->horizontalHeader()->setSectionResizeMode(7, QHeaderView::Stretch);

    root->addWidget(table_);
}

void DxwCandidateMatrix::setCandidateRows(QStringList rows, QString activeCall) {
    static const QChar separator(0x1f);
    activeCall = activeCall.trimmed().toUpper();
    const int visibleRows = std::min(12, rows.size());

    table_->setUpdatesEnabled(false);
    table_->clearContents();
    table_->setRowCount(visibleRows);

    for (int row = 0; row < visibleRows; ++row) {
        QStringList cells = rows.at(row).split(separator);
        while (cells.size() < 12) cells << "-";
        const QString call = cells.value(0).trimmed().toUpper();
        const bool locked = !activeCall.isEmpty() && call == activeCall;

        for (int column = 0; column < 12; ++column) {
            QTableWidgetItem* item = new QTableWidgetItem(cells.value(column));
            if (column == 1 || column == 6 || column == 9 || column == 10)
                item->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
            if (locked) {
                item->setBackground(QBrush(QColor("#3A301A")));
                item->setForeground(QBrush(QColor("#FFE1A3")));
            }
            table_->setItem(row, column, item);
        }

        QTableWidgetItem* target = new QTableWidgetItem(locked ? "LOCKED" : "READY");
        if (locked) {
            target->setBackground(QBrush(QColor("#3A301A")));
            target->setForeground(QBrush(QColor("#FFE1A3")));
        }
        table_->setItem(row, 12, target);
    }

    table_->setUpdatesEnabled(true);
    summary_->setText(QString("%1 ranked | live scorer").arg(rows.size()));
}

} // namespace dxw
