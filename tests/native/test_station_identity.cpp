#include <gtest/gtest.h>
#include "dxw/QsoStateMachine.h"

using namespace dxw;

namespace {
bool hasAction(const std::vector<Action>& actions, ActionType type) {
    for (std::size_t i = 0; i < actions.size(); ++i)
        if (actions[i].type == type) return true;
    return false;
}
}

TEST(StationIdentity, InitializesFromRuntimeIdentityAndUpdatesGridLive) {
    QsoStateMachine sm("PY2ABC", "GG66");
    EXPECT_EQ(sm.myCall(), "PY2ABC");
    EXPECT_EQ(sm.myGrid(), "GG66");

    sm.arm(Strategy::Both);
    const std::vector<Action> actions = sm.updateStationIdentity("PY2ABC", "GG67");
    EXPECT_TRUE(actions.empty());
    EXPECT_TRUE(sm.armed());
    EXPECT_EQ(sm.myCall(), "PY2ABC");
    EXPECT_EQ(sm.myGrid(), "GG67");
}

TEST(StationIdentity, CallsignChangeWhileArmedDisarmsAndStopsActiveQso) {
    QsoStateMachine sm("PY2ABC", "GG66");
    sm.arm(Strategy::Both);
    Candidate target;
    target.call = "9Y4C";
    sm.startHunt(target);

    const std::vector<Action> actions = sm.updateStationIdentity("PY2XYZ", "GG66");
    EXPECT_TRUE(hasAction(actions, ActionType::HaltTx));
    EXPECT_TRUE(hasAction(actions, ActionType::Disarm));
    EXPECT_FALSE(sm.armed());
    EXPECT_EQ(sm.state(), QsoState::Disarmed);
    EXPECT_EQ(sm.myCall(), "PY2XYZ");
    EXPECT_EQ(sm.myGrid(), "GG66");
    EXPECT_TRUE(sm.activeCall().empty());
}

TEST(StationIdentity, CannotArmWithoutCallsign) {
    QsoStateMachine sm("", "GG66");
    const std::vector<Action> actions = sm.arm(Strategy::Both);
    EXPECT_FALSE(sm.armed());
    EXPECT_EQ(sm.state(), QsoState::Disarmed);
    EXPECT_TRUE(hasAction(actions, ActionType::Disarm));
}
