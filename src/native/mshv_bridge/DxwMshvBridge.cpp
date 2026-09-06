#include "DxwMshvBridge.h"

#include <QRegularExpression>
#include <algorithm>

namespace dxw {

DxwMshvBridge::DxwMshvBridge(QString myCall, QObject* parent)
    : QObject(parent), myCall_(myCall.trimmed().toUpper()), sm_(myCall_.toStdString()) {
    clock_.setTimerType(Qt::PreciseTimer);
    clock_.setInterval(50);
    connect(&clock_, SIGNAL(timeout()), this, SLOT(onClock()));
    clock_.start();
}

bool DxwMshvBridge::looksLikeCall(const QString& token) {
    static const QRegularExpression re("^(?=.{3,15}$)(?=.*[A-Z])(?=.*\\d)[A-Z0-9/]+$");
    return re.match(token.toUpper()).hasMatch();
}

bool DxwMshvBridge::looksLikeGrid(const QString& token) {
    static const QRegularExpression re("^[A-R]{2}[0-9]{2}([A-X]{2})?$");
    return re.match(token.toUpper()).hasMatch();
}

ExchangeStage DxwMshvBridge::exchangeStage(const QString& token) {
    const QString t = token.toUpper();
    if (looksLikeGrid(t)) return ExchangeStage::Grid;
    if (t == "RRR") return ExchangeStage::RRR;
    if (t == "RR73") return ExchangeStage::RR73;
    if (t == "73") return ExchangeStage::Final73;
    if (t.startsWith("R+") || t.startsWith("R-")) return ExchangeStage::RReport;
    static const QRegularExpression report("^[+-][0-9]{2}$");
    if (report.match(t).hasMatch()) return ExchangeStage::Report;
    return ExchangeStage::Unknown;
}

QString DxwMshvBridge::findCqCall(const QStringList& tokens) {
    if (tokens.isEmpty() || tokens.at(0).toUpper() != "CQ") return {};
    for (int i = 1; i < tokens.size(); ++i) {
        const QString t = tokens.at(i).toUpper();
        if (looksLikeCall(t)) return t;
    }
    return {};
}

Candidate DxwMshvBridge::candidateFrom(const QStringList& decode, const QString& call) const {
    Candidate c;
    c.call = call.toStdString();
    c.mode = "FT8";
    bool ok = false;
    c.snr = decode.value(1).toInt(&ok);
    if (!ok) c.snr = -30;
    const QStringList tokens = decode.value(4).simplified().toUpper().split(' ', Qt::SkipEmptyParts);
    if (!tokens.isEmpty() && looksLikeGrid(tokens.last())) c.grid = tokens.last().toStdString();
    const auto it = cooldowns_.constFind(call);
    c.cooldownActive = (it != cooldowns_.constEnd() && it.value() > QDateTime::currentDateTimeUtc());
    return c;
}

bool DxwMshvBridge::runnerUp(const QString& excluding, Candidate& result) const {
    std::vector<Candidate> pool;
    pool.reserve(static_cast<std::size_t>(candidates_.size()));
    for (const auto& c : candidates_) {
        if (QString::fromStdString(c.call) != excluding) pool.push_back(c);
    }
    const auto ranked = scorer_.rank(pool);
    if (ranked.empty()) return false;
    result = ranked.front().candidate;
    return true;
}

void DxwMshvBridge::processActions(const std::vector<Action>& actions) {
    for (const auto& action : actions) {
        const QString call = QString::fromStdString(action.call);
        switch (action.type) {
        case ActionType::HaltTx:
            emit haltTxRequested();
            break;
        case ActionType::EnsureAuto:
            emit ensureAutoRequested();
            break;
        case ActionType::SelectTarget:
            if (rawByCall_.contains(call)) emit selectDecode(rawByCall_.value(call));
            break;
        case ActionType::ApplyCooldown:
            if (!call.isEmpty()) cooldowns_.insert(call, QDateTime::currentDateTimeUtc().addSecs(60));
            break;
        default:
            break;
        }
    }
    emitState();
}

void DxwMshvBridge::emitState() {
    QString state;
    switch (sm_.state()) {
    case QsoState::Disarmed: state = "DISARMED"; break;
    case QsoState::Idle: state = "IDLE"; break;
    case QsoState::HuntCalling: state = "HUNT"; break;
    case QsoState::Answering: state = "ANSWER"; break;
    case QsoState::Locked: state = "LOCKED"; break;
    case QsoState::Completing: state = "COMPLETING"; break;
    case QsoState::Fault: state = "FAULT"; break;
    }
    emit stateChanged(state, QString::fromStdString(sm_.activeCall()), candidates_.size());
}

void DxwMshvBridge::setArmed(bool armed) {
    if (armed) processActions(sm_.arm(strategy_));
    else processActions(sm_.disarm("DXWeaver DISARM"));
}

void DxwMshvBridge::setStrategy(int strategy) {
    strategy_ = strategy == 0 ? Strategy::Hunt : strategy == 1 ? Strategy::Answer : Strategy::Both;
    if (sm_.armed()) {
        processActions(sm_.disarm("strategy change"));
        processActions(sm_.arm(strategy_));
    }
    emitState();
}

void DxwMshvBridge::halt() {
    processActions(sm_.halt("DXWeaver HALT TX"));
}

void DxwMshvBridge::onQsoLogged(QStringList) {
    const std::string active = sm_.activeCall();
    if (!active.empty()) processActions(sm_.onQsoLogged(active));
    candidates_.clear();
    rawByCall_.clear();
}

void DxwMshvBridge::onDecode(QStringList decode) {
    if (decode.size() < 5) return;
    const QString message = decode.at(4).simplified().toUpper();
    const QStringList tokens = message.split(' ', Qt::SkipEmptyParts);
    if (tokens.isEmpty()) return;

    const QString active = QString::fromStdString(sm_.activeCall()).toUpper();

    if (tokens.size() >= 2 && tokens.at(0) == myCall_ && looksLikeCall(tokens.at(1))) {
        const QString sender = tokens.at(1);
        rawByCall_.insert(sender, decode);
        Candidate caller = candidateFrom(decode, sender);
        const ExchangeStage stage = tokens.size() >= 3 ? exchangeStage(tokens.at(2)) : ExchangeStage::Unknown;
        if (!active.isEmpty() && sender == active) {
            processActions(sm_.onActiveExchange(sender.toStdString(), stage));
        } else if (stage == ExchangeStage::Grid) {
            processActions(sm_.onDirectedCaller(caller));
        }
        return;
    }

    if (!active.isEmpty() && tokens.size() >= 2 && tokens.at(1) == active && tokens.at(0) != myCall_) {
        const QString third = tokens.at(0);
        if (looksLikeCall(third)) {
            Candidate next;
            const bool hasNext = runnerUp(active, next);
            processActions(sm_.onTargetAnswersThirdParty(
                active.toStdString(), third.toStdString(), hasNext ? &next : nullptr));
            return;
        }
    }

    const QString cqCall = findCqCall(tokens);
    if (cqCall.isEmpty()) return;
    Candidate c = candidateFrom(decode, cqCall);
    rawByCall_.insert(cqCall, decode);

    bool replaced = false;
    for (auto& existing : candidates_) {
        if (QString::fromStdString(existing.call) == cqCall) {
            if (c.snr > existing.snr) existing = c;
            replaced = true;
            break;
        }
    }
    if (!replaced) candidates_.push_back(c);
    emitState();
}

void DxwMshvBridge::onClock() {
    if (!sm_.armed() || sm_.state() != QsoState::Idle || strategy_ == Strategy::Answer) return;
    const QTime t = QDateTime::currentDateTimeUtc().time();
    if (!Ft8SlotClock::isDecisionSecond(t.second())) return;
    if (lastDecisionSecond_ == t.second()) return;
    lastDecisionSecond_ = t.second();

    std::vector<Candidate> pool;
    pool.reserve(static_cast<std::size_t>(candidates_.size()));
    for (const auto& c : candidates_) pool.push_back(c);
    const auto ranked = scorer_.rank(pool);
    if (!ranked.empty()) processActions(sm_.startHunt(ranked.front().candidate));
    candidates_.clear();
}

} // namespace dxw
