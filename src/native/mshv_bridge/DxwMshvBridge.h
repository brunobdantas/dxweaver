#pragma once

#include <QObject>
#include <QDateTime>
#include <QHash>
#include <QSet>
#include <QStringList>
#include <QTimer>
#include <QVector>

#include "../dxw/CandidateScorer.h"
#include "../dxw/CtyResolver.h"
#include "../dxw/Ft8SlotClock.h"
#include "../dxw/HuntWatchdog.h"
#include "../dxw/QsoStateMachine.h"
#include "DxwHistoryCache.h"
#include "../../HvTxW/hvqthloc.h"

namespace dxw {

class DxwMshvBridge final : public QObject {
    Q_OBJECT
public:
    explicit DxwMshvBridge(QString myCall,
                           QString myGrid,
                           QString band,
                           QString appPath,
                           QObject* parent = nullptr);

    QString stationCall() const { return myCall_; }
    QString stationGrid() const { return myGrid_; }
    QString currentBand() const { return band_; }
    bool historyAvailable() const noexcept { return history_.available(); }

signals:
    void selectDecode(QStringList decode);
    void selectHuntDecode(QString allText, QString selectedCall, QString time, QString txReport, QString freq);
    void haltTxRequested();
    void ensureAutoRequested();
    void stateChanged(QString state, QString activeCall, int candidateCount);
    void candidateMatrixChanged(QStringList rows, QString activeCall);

public slots:
    void onDecode(QStringList decode);
    void onQsoLogged(QStringList);
    void setStationIdentity(QString call, QString grid);
    void setBand(QString band);
    void setArmed(bool armed);
    void setStrategy(int strategy);
    void halt();

private slots:
    void onClock();

private:
    static bool looksLikeCall(const QString& token);
    static bool looksLikeGrid(const QString& token);
    static ExchangeStage exchangeStage(const QString& token);
    static QString findCqCall(const QStringList& tokens);

    Candidate candidateFrom(const QStringList& decode, const QString& call);
    void upsertCandidate(const Candidate& candidate);
    void publishCandidateMatrix(bool rebuildRows);
    void processActions(const std::vector<Action>& actions);
    void emitState();
    bool runnerUp(const QString& excluding, Candidate& result) const;
    bool freshCqCandidate(const QString& call, const QDateTime& now) const;
    std::vector<Candidate> freshHuntPool(const QDateTime& now, const QString& excluding = QString()) const;
    void clearCandidateWindow();

    QString myCall_;
    QString myGrid_;
    QString band_;
    QString appPath_;
    Strategy strategy_{Strategy::Both};
    QsoStateMachine sm_;
    CandidateScorer scorer_;
    CtyResolver cty_;
    DxwHistoryCache history_;
    HvQthLoc qth_;
    HuntWatchdog huntWatchdog_;
    QTimer clock_;
    QVector<Candidate> candidates_;
    QHash<QString, QStringList> rawByCall_;
    QHash<QString, QDateTime> cooldowns_;
    QHash<QString, QDateTime> lastSeenByCall_;
    QSet<QString> cqCandidates_;
    QStringList matrixRows_;
    int lastDecisionSecond_{-1};
};

} // namespace dxw
