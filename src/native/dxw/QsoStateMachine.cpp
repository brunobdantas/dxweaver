#include "QsoStateMachine.h"
#include <utility>

namespace dxw {

QsoStateMachine::QsoStateMachine(std::string myCall, std::string myGrid)
    : myCall_(std::move(myCall)), myGrid_(std::move(myGrid)) {}

bool QsoStateMachine::allowsHunt() const noexcept {
    return strategy_ == Strategy::Hunt || strategy_ == Strategy::Both;
}

bool QsoStateMachine::allowsAnswer() const noexcept {
    return strategy_ == Strategy::Answer || strategy_ == Strategy::Both;
}

void QsoStateMachine::setTarget(const Candidate& c, TargetKind kind) {
    activeCall_ = c.call;
    activeKind_ = kind;
}

void QsoStateMachine::clearTarget() noexcept {
    activeCall_.clear();
    activeKind_ = TargetKind::None;
    engaged_ = false;
}

std::vector<Action> QsoStateMachine::arm(Strategy strategy) {
    if (myCall_.empty()) {
        armed_ = false;
        state_ = QsoState::Disarmed;
        return {{ActionType::Disarm, {}, "cannot arm without station callsign"}};
    }
    strategy_ = strategy;
    armed_ = true;
    if (state_ == QsoState::Disarmed || state_ == QsoState::Fault) state_ = QsoState::Idle;
    return {{ActionType::EnsureAuto, {}, "automation armed"}};
}

std::vector<Action> QsoStateMachine::disarm(std::string reason) {
    std::vector<Action> actions;
    if (state_ == QsoState::HuntCalling || state_ == QsoState::Answering ||
        state_ == QsoState::Locked || state_ == QsoState::Completing) {
        actions.push_back({ActionType::HaltTx, activeCall_, reason});
    }
    clearTarget();
    armed_ = false;
    state_ = QsoState::Disarmed;
    actions.push_back({ActionType::Disarm, {}, std::move(reason)});
    return actions;
}

std::vector<Action> QsoStateMachine::halt(std::string reason) {
    const std::string callBefore = activeCall_;
    std::vector<Action> actions = disarm(reason);
    if (actions.empty() || actions.front().type != ActionType::HaltTx)
        actions.insert(actions.begin(), {ActionType::HaltTx, callBefore, reason});
    return actions;
}

std::vector<Action> QsoStateMachine::updateStationIdentity(std::string myCall, std::string myGrid) {
    const bool callChanged = myCall != myCall_;
    const bool gridChanged = myGrid != myGrid_;
    if (!callChanged && !gridChanged) return {};

    std::vector<Action> actions;
    if (callChanged && armed_) {
        actions = disarm("station callsign changed");
    }
    myCall_ = std::move(myCall);
    myGrid_ = std::move(myGrid);
    return actions;
}

std::vector<Action> QsoStateMachine::startHunt(const Candidate& candidate) {
    if (!armed_ || !allowsHunt() || state_ != QsoState::Idle) return {};
    setTarget(candidate, TargetKind::Hunt);
    engaged_ = false;
    state_ = QsoState::HuntCalling;
    return {
        {ActionType::EnsureAuto, candidate.call, "native AutoSeq must own exchange"},
        {ActionType::SelectTarget, candidate.call, "highest ranked HUNT candidate"},
        {ActionType::StartHunt, candidate.call, "start native HUNT"}
    };
}

std::vector<Action> QsoStateMachine::onDirectedCaller(const Candidate& caller) {
    if (!armed_ || !allowsAnswer()) return {};

    if (state_ == QsoState::Locked || state_ == QsoState::Completing ||
        (state_ == QsoState::HuntCalling && engaged_)) {
        return {{ActionType::IgnoreCaller, caller.call, "active QSO is locked"}};
    }

    std::vector<Action> actions;
    if (state_ == QsoState::HuntCalling && !engaged_) {
        const std::string old = activeCall_;
        actions.push_back({ActionType::HaltTx, old, "directed caller preempts unanswered HUNT"});
        actions.push_back({ActionType::ApplyCooldown, old, "preempted unanswered HUNT"});
        actions.push_back({ActionType::ClearTarget, old, "release unanswered HUNT target"});
    } else if (state_ != QsoState::Idle && state_ != QsoState::Answering) {
        return {};
    }

    setTarget(caller, TargetKind::DirectedCaller);
    engaged_ = true;
    state_ = QsoState::Locked;
    actions.push_back({ActionType::EnsureAuto, caller.call, "native AutoSeq/MultiAnswer"});
    actions.push_back({ActionType::SelectTarget, caller.call, "directed caller has absolute priority"});
    actions.push_back({ActionType::StartAnswer, caller.call, "answer directed caller"});
    actions.push_back({ActionType::LockTarget, caller.call, "directed caller locked"});
    return actions;
}

std::vector<Action> QsoStateMachine::onActiveExchange(const std::string& fromCall, ExchangeStage stage) {
    if (!armed_ || fromCall.empty() || fromCall != activeCall_) return {};
    if (!isEngagingStage(stage)) return {};

    engaged_ = true;
    if (stage == ExchangeStage::RR73 || stage == ExchangeStage::Final73)
        state_ = QsoState::Completing;
    else
        state_ = QsoState::Locked;

    return {{ActionType::LockTarget, activeCall_, "directed exchange received from active target"}};
}

std::vector<Action> QsoStateMachine::onTargetAnswersThirdParty(
    const std::string& targetCall,
    const std::string& thirdParty,
    const Candidate* nextCandidate) {
    if (!armed_ || targetCall.empty() || targetCall != activeCall_) return {};
    if (activeKind_ != TargetKind::Hunt) return {};

    std::vector<Action> actions{
        {ActionType::HaltTx, activeCall_, "target is working " + thirdParty},
        {ActionType::ApplyCooldown, activeCall_, "target busy with third party"},
        {ActionType::ClearTarget, activeCall_, "busy target released"}
    };
    clearTarget();
    state_ = QsoState::Idle;

    if (nextCandidate != nullptr && allowsHunt()) {
        std::vector<Action> next = startHunt(*nextCandidate);
        actions.insert(actions.end(), next.begin(), next.end());
    }
    return actions;
}

std::vector<Action> QsoStateMachine::onQsoLogged(const std::string& call) {
    if (call.empty() || (!activeCall_.empty() && call != activeCall_)) return {};
    const std::string old = activeCall_;
    clearTarget();
    state_ = armed_ ? QsoState::Idle : QsoState::Disarmed;
    return {{ActionType::ClearTarget, old, "QSO logged"}};
}

std::vector<Action> QsoStateMachine::onTimeout(const Candidate* nextCandidate) {
    if (!armed_ || activeCall_.empty()) return {};
    const std::string old = activeCall_;
    std::vector<Action> actions{
        {ActionType::HaltTx, old, "QSO timeout"},
        {ActionType::ApplyCooldown, old, "timeout"},
        {ActionType::ClearTarget, old, "timeout"}
    };
    clearTarget();
    state_ = QsoState::Idle;
    if (nextCandidate != nullptr && allowsHunt()) {
        std::vector<Action> next = startHunt(*nextCandidate);
        actions.insert(actions.end(), next.begin(), next.end());
    }
    return actions;
}

std::vector<Action> QsoStateMachine::onCatLost(bool pttWasActive) {
    std::vector<Action> actions;
    if (pttWasActive || state_ == QsoState::HuntCalling || state_ == QsoState::Answering ||
        state_ == QsoState::Locked || state_ == QsoState::Completing) {
        actions.push_back({ActionType::HaltTx, activeCall_, "CAT/VFO lost: fail-safe PTT release"});
    }
    clearTarget();
    armed_ = false;
    state_ = QsoState::Fault;
    actions.push_back({ActionType::Disarm, {}, "CAT/VFO lost"});
    actions.push_back({ActionType::EnterFault, {}, "CAT/VFO lost"});
    return actions;
}

} // namespace dxw
