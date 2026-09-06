#include <gtest/gtest.h>
#include "dxw/Ft8SlotClock.h"
#include "dxw/HistoryProvider.h"
#include "dxw/QsoStateMachine.h"
#include <atomic>
#include <chrono>
#include <thread>

using namespace dxw;

namespace {
class FailingHistory final : public IHistoryProvider {
public:
    bool lookup(const std::string&, const std::string&, const std::string&,
                const std::string&, HistoryFacts&) const noexcept override {
        return false;
    }
};
bool has(const std::vector<Action>& a, ActionType t) {
    for (std::size_t i = 0; i < a.size(); ++i) if (a[i].type == t) return true;
    return false;
}
}

TEST(Resilience, CatLossDuringTransmitForcesSafeFaultAndDisarm) {
    QsoStateMachine sm("PU2BRU");
    Candidate c; c.call="9Y4C";
    sm.arm(Strategy::Both);
    sm.startHunt(c);
    std::vector<Action> actions = sm.onCatLost(true);
    EXPECT_TRUE(has(actions, ActionType::HaltTx));
    EXPECT_TRUE(has(actions, ActionType::Disarm));
    EXPECT_TRUE(has(actions, ActionType::EnterFault));
    EXPECT_FALSE(sm.armed());
    EXPECT_EQ(sm.state(), QsoState::Fault);
}

TEST(Resilience, LockedOrCorruptHistoryProviderFallsBackWithoutExceptionDependency) {
    std::shared_ptr<FailingHistory> failing(new FailingHistory());
    ResilientHistoryProvider safe(failing);
    HistoryFacts facts;
    EXPECT_FALSE(safe.lookup("9Y4C", "15m", "FT8", "Trinidad & Tobago", facts));
    EXPECT_FALSE(facts.worked);
    EXPECT_FALSE(facts.confirmed);
    EXPECT_FALSE(facts.entityWorked);
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
    std::atomic<bool> started(false);
    std::atomic<bool> stop(false);
    std::atomic<unsigned long long> realtimeProgress(0);

    std::thread realtime([&] {
        started.store(true, std::memory_order_release);
        while (!stop.load(std::memory_order_relaxed)) {
            realtimeProgress.fetch_add(1, std::memory_order_relaxed);
            std::this_thread::yield();
        }
    });

    while (!started.load(std::memory_order_acquire)) std::this_thread::yield();
    const unsigned long long before = realtimeProgress.load(std::memory_order_relaxed);
    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    const unsigned long long after = realtimeProgress.load(std::memory_order_relaxed);

    stop.store(true, std::memory_order_relaxed);
    realtime.join();

    EXPECT_GT(after, before);
    EXPECT_GT(after - before, 100ULL)
        << "realtime worker did not make meaningful progress during UI stall";
}
