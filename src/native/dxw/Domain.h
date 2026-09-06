#pragma once

#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace dxw {

enum class Strategy { Hunt, Answer, Both };
enum class QsoState { Disarmed, Idle, HuntCalling, Answering, Locked, Completing, Fault };
enum class TargetKind { None, Hunt, DirectedCaller };
enum class ExchangeStage { Grid, Report, RReport, RRR, RR73, Final73, Unknown };

enum class ActionType {
    HaltTx,
    EnsureAuto,
    SelectTarget,
    StartHunt,
    StartAnswer,
    LockTarget,
    ClearTarget,
    ApplyCooldown,
    IgnoreCaller,
    Disarm,
    EnterFault
};

struct Action {
    ActionType type;
    std::string call;
    std::string reason;

    Action() : type(ActionType::HaltTx) {}
    Action(ActionType actionType, std::string actionCall, std::string actionReason)
        : type(actionType), call(actionCall), reason(actionReason) {}
};

struct Candidate {
    std::string call;
    std::string grid;
    std::string entity;
    std::string continent;
    std::string band;
    std::string mode{"FT8"};
    int cqZone{0};
    int ituZone{0};
    int snr{-30};
    int azimuthDeg{0};
    double distanceKm{0.0};
    bool newDxcc{false};
    bool newBand{false};
    bool newMode{false};
    bool newSlot{false};
    bool lotw{false};
    bool eqsl{false};
    bool watchlist{false};
    bool confirmed{false};
    bool worked{false};
    bool cooldownActive{false};
};

struct ScoreBreakdown {
    int total{0};
    int newDxcc{0};
    int newBand{0};
    int newMode{0};
    int newSlot{0};
    int lotw{0};
    int eqsl{0};
    int watchlist{0};
    int unconfirmed{0};
    int snr{0};
    int distance{0};
    int workedPenalty{0};
    int cooldownPenalty{0};
};

struct RankedCandidate {
    Candidate candidate;
    ScoreBreakdown score;
};

inline bool isEngagingStage(ExchangeStage stage) noexcept {
    return stage == ExchangeStage::Report || stage == ExchangeStage::RReport ||
           stage == ExchangeStage::RRR || stage == ExchangeStage::RR73 ||
           stage == ExchangeStage::Final73;
}

} // namespace dxw
