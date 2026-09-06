#include "DxwMshvBridge.h"

#include <QCoreApplication>
#include <QDir>
#include <QRegularExpression>
#include <algorithm>

namespace dxw {
namespace {

QString newFlag(bool value) {
    return value ? QStringLiteral("NEW") : QStringLiteral("-");
}

QString historyLabel(const Candidate& candidate) {
    if (candidate.confirmed) return QStringLiteral("CONFIRMED");
    if (candidate.worked) return QStringLiteral("WORKED");
    return QStringLiteral("-");
}

} // namespace

DxwMshvBridge::DxwMshvBridge(QString myCall,
                             QString myGrid,
                             QString band,
                             QString appPath,
                             QObject* parent)
    : QObject(parent),
      myCall_(myCall.trimmed().toUpper()),
      myGrid_(myGrid.trimmed().toUpper()),
      band_(band.trimmed().toLower()),
      appPath_(appPath),
      sm_(myCall_.toStdString(), myGrid_.toStdString()),
      history_(appPath_) {
    const QString ctyPath = QDir(QCoreApplication::applicationDirPath()).filePath("settings/database/cty.dat");
    cty_.load(ctyPath.toStdString());
    history_.reload();

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
    if (tokens.isEmpty() || tokens.at(0).toUpper() != "CQ") return QString();
    for (int i = 1; i < tokens.size(); ++i) {
        const QString t = tokens.at(i).toUpper();
        if (looksLikeCall(t)) return t;
    }
    return QString();
}

Candidate DxwMshvBridge::candidateFrom(const QStringList& decode, const QString& call) {
    Candidate c;
    c.call = call.toUpper().toStdString();
    c.mode = "FT8";
    c.band = band_.toStdString();

    bool ok = false;
    c.snr = decode.value(1).toInt(&ok);
    if (!ok) c.snr = -30;

    const QStringList tokens = decode.value(4).simplified().toUpper().split(' ', Qt::SkipEmptyParts);
    if (!tokens.isEmpty() && looksLikeGrid(tokens.last())) c.grid = tokens.last().toStdString();

    CtyEntity entity;
    if (cty_.resolve(c.call, entity)) {
        c.entity = entity.country;
        c.continent = entity.continent;
        c.cqZone = entity.cqZone;
        c.ituZone = entity.ituZone;
    }

    const QString remoteGrid = QString::fromStdString(c.grid).toUpper();
    if (!myGrid_.isEmpty() && !remoteGrid.isEmpty() &&
        qth_.isValidLocator(myGrid_) && qth_.isValidLocator(remoteGrid)) {
        const double myLon = qth_.getLon(myGrid_);
        const double myLat = qth_.getLat(myGrid_);
        const double dxLon = qth_.getLon(remoteGrid);
        const double dxLat = qth_.getLat(remoteGrid);
        c.distanceKm = qth_.getDistanceKilometres(myLon, myLat, dxLon, dxLat);
        c.azimuthDeg = qth_.getBeam(myLon, myLat, dxLon, dxLat);
    }

    if (history_.available()) {
        const HistoryFacts facts = history_.lookup(c.call, c.band, c.mode, c.entity);
        c.worked = facts.worked;
        c.confirmed = facts.confirmed;
        if (!c.entity.empty()) {
            c.newDxcc = !facts.entityWorked;
            c.newBand = !c.band.empty() && !facts.entityBandWorked;
            c.newMode = !facts.entityModeWorked;
            c.newSlot = !c.band.empty() && !facts.entitySlotWorked;
        } else {
            c.newBand = !c.band.empty() && !facts.workedBand;
            c.newMode = !facts.workedMode;
            c.newSlot = !c.band.empty() && !facts.workedSlot;
        }
    }

    const QHash<QString, QDateTime>::const_iterator it = cooldowns_.constFind(call.toUpper());
    c.cooldownActive = (it != cooldowns_.constEnd() && it.value() > QDateTime::currentDateTimeUtc());
    return c;
}

void DxwMshvBridge::upsertCandidate(const Candidate& candidate) {
    const QString call = QString::fromStdString(candidate.call).toUpper();
    for (QVector<Candidate>::iterator it = candidates_.begin(); it != candidates_.end(); ++it) {
        if (QString::fromStdString(it->call).toUpper() != call) continue;
        const bool gainedGrid = it->grid.empty() && !candidate.grid.empty();
        if (candidate.snr >= it->snr || gainedGrid) *it = candidate;
        return;
    }
    candidates_.push_back(candidate);
}

void DxwMshvBridge::publishCandidateMatrix(bool rebuildRows) {
    if (rebuildRows) {
        matrixRows_.clear();
        std::vector<Candidate> pool;
        pool.reserve(static_cast<std::size_t>(candidates_.size()));
        for (QVector<Candidate>::const_iterator it = candidates_.constBegin(); it != candidates_.constEnd(); ++it)
            pool.push_back(*it);

        const std::vector<RankedCandidate> ranked = scorer_.rank(pool);
        const int limit = std::min(20, static_cast<int>(ranked.size()));
        const QChar separator(0x1f);
        for (int i = 0; i < limit; ++i) {
            const RankedCandidate& rankedCandidate = ranked.at(static_cast<std::size_t>(i));
            const Candidate& c = rankedCandidate.candidate;
            const QString zone = (c.cqZone > 0 || c.ituZone > 0)
                ? QString("%1/%2").arg(c.cqZone).arg(c.ituZone)
                : QStringLiteral("-");
            QStringList cells;
            cells << QString::fromStdString(c.call)
                  << QString::number(rankedCandidate.score.total)
                  << newFlag(c.newDxcc)
                  << newFlag(c.newBand)
                  << newFlag(c.newMode)
                  << newFlag(c.newSlot)
                  << QString::number(c.snr)
                  << (c.entity.empty() ? QStringLiteral("-") : QString::fromStdString(c.entity))
                  << zone
                  << QString::number(c.distanceKm, 'f', 0)
                  << QString::number(c.azimuthDeg)
                  << historyLabel(c);
            matrixRows_ << cells.join(separator);
        }
    }

    emit candidateMatrixChanged(matrixRows_, QString::fromStdString(sm_.activeCall()));
}

bool DxwMshvBridge::runnerUp(const QString& excluding, Candidate& result) const {
    std::vector<Candidate> pool;
    pool.reserve(static_cast<std::size_t>(candidates_.size()));
    for (QVector<Candidate>::const_iterator it = candidates_.constBegin(); it != candidates_.constEnd(); ++it) {
        if (QString::fromStdString(it->call) != excluding) pool.push_back(*it);
    }
    const std::vector<RankedCandidate> ranked = scorer_.rank(pool);
    if (ranked.empty()) return false;
    result = ranked.front().candidate;
    return true;
}

void DxwMshvBridge::processActions(const std::vector<Action>& actions) {
    for (std::vector<Action>::const_iterator it = actions.begin(); it != actions.end(); ++it) {
        const QString call = QString::fromStdString(it->call);
        switch (it->type) {
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
    publishCandidateMatrix(false);
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

void DxwMshvBridge::setStationIdentity(QString call, QString grid) {
    call = call.trimmed().toUpper();
    grid = grid.trimmed().toUpper();
    const std::vector<Action> actions = sm_.updateStationIdentity(call.toStdString(), grid.toStdString());
    myCall_ = call;
    myGrid_ = grid;
    candidates_.clear();
    rawByCall_.clear();
    matrixRows_.clear();
    if (!actions.empty()) processActions(actions);
    else {
        emitState();
        publishCandidateMatrix(false);
    }
}

void DxwMshvBridge::setBand(QString band) {
    band = band.trimmed().toLower();
    if (band == band_) return;
    band_ = band;
    candidates_.clear();
    rawByCall_.clear();
    matrixRows_.clear();
    emitState();
    publishCandidateMatrix(false);
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
    publishCandidateMatrix(false);
}

void DxwMshvBridge::halt() {
    processActions(sm_.halt("DXWeaver HALT TX"));
}

void DxwMshvBridge::onQsoLogged(QStringList) {
    const std::string active = sm_.activeCall();
    if (!active.empty()) processActions(sm_.onQsoLogged(active));
    candidates_.clear();
    rawByCall_.clear();
    matrixRows_.clear();
    history_.reload();
    emitState();
    publishCandidateMatrix(false);
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
        upsertCandidate(caller);
        publishCandidateMatrix(true);
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
    upsertCandidate(c);
    emitState();
    publishCandidateMatrix(true);
}

void DxwMshvBridge::onClock() {
    if (!sm_.armed() || sm_.state() != QsoState::Idle || strategy_ == Strategy::Answer) return;
    const QTime t = QDateTime::currentDateTimeUtc().time();
    if (!Ft8SlotClock::isDecisionSecond(t.second())) return;
    if (lastDecisionSecond_ == t.second()) return;
    lastDecisionSecond_ = t.second();

    std::vector<Candidate> pool;
    pool.reserve(static_cast<std::size_t>(candidates_.size()));
    for (QVector<Candidate>::const_iterator it = candidates_.constBegin(); it != candidates_.constEnd(); ++it)
        pool.push_back(*it);
    const std::vector<RankedCandidate> ranked = scorer_.rank(pool);
    publishCandidateMatrix(true);
    if (!ranked.empty()) processActions(sm_.startHunt(ranked.front().candidate));
    candidates_.clear();
    emitState();
}

} // namespace dxw
