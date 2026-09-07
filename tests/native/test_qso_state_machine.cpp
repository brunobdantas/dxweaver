#include <gtest/gtest.h>
#include "dxw/QsoStateMachine.h"

using namespace dxw;

namespace {
Candidate c(std::string call) { Candidate x; x.call = std::move(call); x.mode = "FT8"; x.band = "15m"; return x; }
bool has(const std::vector<Action>& a, ActionType t, const std::string& call = {}) {
    for (const auto& x : a) if (x.type == t && (call.empty() || x.call == call)) return true;
    return false;
}
int indexOf(const std::vector<Action>& a, ActionType t) {
    for (std::size_t i = 0; i < a.size(); ++i) if (a[i].type == t) return static_cast<int>(i);
    return -1;
}
}

TEST(QsoStateMachine, DirectedCallerPreemptsUnansweredHuntAndLocksCaller) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Both);
    sm.startHunt(c("9Y4C"));
    ASSERT_EQ(sm.state(), QsoState::HuntCalling);
    ASSERT_FALSE(sm.engaged());

    auto actions = sm.onDirectedCaller(c("LU2DPG"));
    EXPECT_TRUE(has(actions, ActionType::HaltTx, "9Y4C"));
    EXPECT_TRUE(has(actions, ActionType::ApplyCooldown, "9Y4C"));
    EXPECT_TRUE(has(actions, ActionType::SelectTarget, "LU2DPG"));
    EXPECT_FALSE(has(actions, ActionType::SelectHuntTarget, "LU2DPG"));
    EXPECT_TRUE(has(actions, ActionType::StartAnswer, "LU2DPG"));
    EXPECT_TRUE(has(actions, ActionType::LockTarget, "LU2DPG"));
    EXPECT_EQ(sm.activeCall(), "LU2DPG");
    EXPECT_EQ(sm.activeKind(), TargetKind::DirectedCaller);
    EXPECT_EQ(sm.state(), QsoState::Locked);
    EXPECT_TRUE(sm.engaged());
}

TEST(QsoStateMachine, EngagedHuntIsInviolableAgainstNewCaller) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Both);
    sm.startHunt(c("9Y4C"));
    auto lockActions = sm.onActiveExchange("9Y4C", ExchangeStage::RReport);
    ASSERT_TRUE(has(lockActions, ActionType::LockTarget, "9Y4C"));
    ASSERT_EQ(sm.state(), QsoState::Locked);

    auto actions = sm.onDirectedCaller(c("LU2DPG"));
    EXPECT_TRUE(has(actions, ActionType::IgnoreCaller, "LU2DPG"));
    EXPECT_FALSE(has(actions, ActionType::HaltTx));
    EXPECT_FALSE(has(actions, ActionType::SelectTarget, "LU2DPG"));
    EXPECT_FALSE(has(actions, ActionType::SelectHuntTarget, "LU2DPG"));
    EXPECT_EQ(sm.activeCall(), "9Y4C");
    EXPECT_EQ(sm.state(), QsoState::Locked);
}

TEST(QsoStateMachine, BusyHuntTargetAbortsAndSelectsRunnerUp) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Hunt);
    sm.startHunt(c("9Y4C"));
    Candidate next = c("IZ0DHC");

    auto actions = sm.onTargetAnswersThirdParty("9Y4C", "KK4CDK", &next);
    EXPECT_TRUE(has(actions, ActionType::HaltTx, "9Y4C"));
    EXPECT_TRUE(has(actions, ActionType::ApplyCooldown, "9Y4C"));
    EXPECT_TRUE(has(actions, ActionType::SelectHuntTarget, "IZ0DHC"));
    EXPECT_FALSE(has(actions, ActionType::SelectTarget, "IZ0DHC"));
    EXPECT_TRUE(has(actions, ActionType::StartHunt, "IZ0DHC"));
    EXPECT_EQ(sm.activeCall(), "IZ0DHC");
    EXPECT_EQ(sm.state(), QsoState::HuntCalling);
}

TEST(QsoStateMachine, BusyTargetCanBreakLockAsProtectionException) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Both);
    sm.startHunt(c("9Y4C"));
    sm.onActiveExchange("9Y4C", ExchangeStage::Report);
    ASSERT_EQ(sm.state(), QsoState::Locked);

    auto actions = sm.onTargetAnswersThirdParty("9Y4C", "EA1XXX");
    EXPECT_TRUE(has(actions, ActionType::HaltTx, "9Y4C"));
    EXPECT_TRUE(has(actions, ActionType::ApplyCooldown, "9Y4C"));
    EXPECT_EQ(sm.state(), QsoState::Idle);
}

TEST(QsoStateMachine, QsoCompletesOnlyForActiveTarget) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Both);
    sm.startHunt(c("9Y4C"));
    sm.onActiveExchange("9Y4C", ExchangeStage::RR73);
    ASSERT_EQ(sm.state(), QsoState::Completing);
    EXPECT_TRUE(sm.onQsoLogged("OTHER").empty());
    EXPECT_EQ(sm.activeCall(), "9Y4C");
    auto actions = sm.onQsoLogged("9Y4C");
    EXPECT_TRUE(has(actions, ActionType::ClearTarget, "9Y4C"));
    EXPECT_EQ(sm.state(), QsoState::Idle);
    EXPECT_TRUE(sm.activeCall().empty());
}

TEST(QsoStateMachine, NativeAutoIsEnsuredBeforeDedicatedHuntSelection) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Hunt);
    const auto actions = sm.startHunt(c("9Y4C"));
    ASSERT_GE(indexOf(actions, ActionType::EnsureAuto), 0);
    ASSERT_GE(indexOf(actions, ActionType::SelectHuntTarget), 0);
    EXPECT_LT(indexOf(actions, ActionType::EnsureAuto), indexOf(actions, ActionType::SelectHuntTarget));
    EXPECT_FALSE(has(actions, ActionType::SelectTarget, "9Y4C"));
}

TEST(QsoStateMachine, UnansweredHuntTimeoutHaltsAndMovesToFreshRunnerUp) {
    QsoStateMachine sm("PU2BRU");
    sm.arm(Strategy::Hunt);
    sm.startHunt(c("YV6BXN"));
    Candidate next = c("PT2OP");

    const auto actions = sm.onTimeout(&next);
    EXPECT_TRUE(has(actions, ActionType::HaltTx, "YV6BXN"));
    EXPECT_TRUE(has(actions, ActionType::ApplyCooldown, "YV6BXN"));
    EXPECT_TRUE(has(actions, ActionType::ClearTarget, "YV6BXN"));
    EXPECT_TRUE(has(actions, ActionType::SelectHuntTarget, "PT2OP"));
    EXPECT_TRUE(has(actions, ActionType::StartHunt, "PT2OP"));
    EXPECT_EQ(sm.activeCall(), "PT2OP");
    EXPECT_EQ(sm.state(), QsoState::HuntCalling);
}
