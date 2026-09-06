#pragma once

#include <QObject>
#include <QDateTime>
#include <QHash>
#include <QStringList>
#include <QTimer>
#include <QVector>

#include "../dxw/CandidateScorer.h"
#include "../dxw/Ft8SlotClock.h"
#include "../dxw/QsoStateMachine.h"

namespace dxw {

class DxwMshvBridge final : public QObject {
    Q_OBJECT
public:
    explicit DxwMshvBridge(QString myCall, QObject* parent = nullptr);

signals:
    void selectDecode(QStringList decode);
    void haltTxRequested();
    void ensureAutoRequested();
    void stateChanged(QString state, QString activeCall, int candidateCount);

public slots:
    void onDecode(QStringList decode);
    void onQsoLogged(QStringList);
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

    Candidate candidateFrom(const QStringList& decode, const QString& call) const;
    void processActions(const std::vector<Action>& actions);
    void emitState();
    bool runnerUp(const QString& excluding, Candidate& result) const;

    QString myCall_;
    Strategy strategy_{Strategy::Both};
    QsoStateMachine sm_;
    CandidateScorer scorer_;
    QTimer clock_;
    QVector<Candidate> candidates_;
    QHash<QString, QStringList> rawByCall_;
    QHash<QString, QDateTime> cooldowns_;
    int lastDecisionSecond_{-1};
};

} // namespace dxw
