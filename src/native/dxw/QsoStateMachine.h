#pragma once

#include "Domain.h"
#include <string>
#include <vector>

namespace dxw {

class QsoStateMachine final {
public:
    explicit QsoStateMachine(std::string myCall);

    QsoState state() const noexcept { return state_; }
    Strategy strategy() const noexcept { return strategy_; }
    bool armed() const noexcept { return armed_; }
    bool engaged() const noexcept { return engaged_; }
    const std::string& activeCall() const noexcept { return activeCall_; }
    TargetKind activeKind() const noexcept { return activeKind_; }

    std::vector<Action> arm(Strategy strategy);
    std::vector<Action> disarm(std::string reason = "operator disarm");
    std::vector<Action> halt(std::string reason = "operator HALT TX");

    std::vector<Action> startHunt(const Candidate& candidate);
    std::vector<Action> onDirectedCaller(const Candidate& caller);
    std::vector<Action> onActiveExchange(const std::string& fromCall, ExchangeStage stage);
    std::vector<Action> onTargetAnswersThirdParty(const std::string& targetCall,
                                                   const std::string& thirdParty,
                                                   const Candidate* nextCandidate = nullptr);
    std::vector<Action> onQsoLogged(const std::string& call);
    std::vector<Action> onTimeout(const Candidate* nextCandidate = nullptr);
    std::vector<Action> onCatLost(bool pttWasActive);

private:
    void setTarget(const Candidate& c, TargetKind kind);
    void clearTarget() noexcept;
    bool allowsHunt() const noexcept;
    bool allowsAnswer() const noexcept;

    std::string myCall_;
    Strategy strategy_{Strategy::Both};
    QsoState state_{QsoState::Disarmed};
    bool armed_{false};
    bool engaged_{false};
    std::string activeCall_;
    TargetKind activeKind_{TargetKind::None};
};

} // namespace dxw
