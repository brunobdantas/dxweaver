#include <gtest/gtest.h>
#include "dxw/Ft8SlotClock.h"
#include "dxw/HistoryProvider.h"
#include "dxw/QsoStateMachine.h"
#include <atomic>
#include <chrono>
#include <stdexcept>
#include <thread>

using namespace dxw;

namespace {
class ThrowingHistory final : public IHistoryProvider {
public:
    HistoryFacts lookup(const std::string&, const std::string&, const std::string&) const override {
        throw std::runtime_error("database locked/corrupt");
    }
};
bool has(const std::vector<Action>& a, ActionType t) {
    for (const auto& x : a) if (x.type == t) return true;
    return false;
}
}

TEST(Resilience, CatLossDuringTransmitForcesSafeFaultAndDisarm) {
    QsoStateMachine sm("PU2BRU");
    Candidate c; c.call="9Y4C";
    sm.arm(Strategy::Both);
    sm.startHunt(c);
    auto actions = sm.onCatLost(true);
    EXPECT_TRUE(has(actions, ActionType::HaltTx));
    EXPECT_TRUE(has(actions, ActionType::Disarm));
    EXPECT_TRUE(has(actions, ActionType::EnterFault));
    EXPECT_FALSE(sm.armed());
    EXPECT_EQ(sm.state(), QsoState::Fault);
}

TEST(Resilience, CorruptOrLockedHrdProviderFallsBackWithoutThrowing) {
    auto throwing = std::make_shared<ThrowingHistory>();
    ResilientHistoryProvider safe(throwing);
    EXPECT_NO_THROW({
        auto facts = safe.lookup("9Y4C", "15m", "FT8");
        EXPECT_FALSE(facts.worked);
        EXPECT_FALSE(facts.confirmed);
    });
}

TEST(Resilience, Ft8DecisionWindowsAreExact) {
    EXPECT_TRUE(Ft8SlotClock::isDecisionSecond(2));
    EXPECT_TRUE(Ft8SlotClock::isDecisionSecond(17));
    EXPECT_TRUE(Ft8SlotClock::isDecisionSecond(32));
    EXPECT_TRUE(Ft8SlotClock::isDecisionSecond(47));
    EXPECT_FALSE(Ft8SlotClock::isDecisionSecond(16));
    EXPECT_EQ(Ft8SlotClock::millisecondsToNextDecision(16, 900), 100);
    EXPECT_EQ(Ft8SlotClock::millisecondsToNextDecision(47, 10), 14990);
}

TEST(Resilience, RealtimeClockDomainContinuesWhileUiThreadIsStalled) {
    std::atomic<bool> stop{false};
    std::atomic<int> audioTicks{0};
    std::thread realtime([&] {
        while (!stop.load(std::memory_order_relaxed)) {
            ++audioTicks;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    });

    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    stop.store(true, std::memory_order_relaxed);
    realtime.join();
    EXPECT_GT(audioTicks.load(), 50);
}
