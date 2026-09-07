#include <gtest/gtest.h>
#include "dxw/HuntWatchdog.h"

using namespace dxw;

TEST(HuntWatchdog, UnansweredTargetExpiresWhenItDisappears) {
    HuntWatchdog watchdog;
    watchdog.start("YV6BXN", 1000);

    EXPECT_FALSE(watchdog.shouldExpire(1000 + HuntWatchdog::kStaleAfterMs - 1));
    EXPECT_TRUE(watchdog.shouldExpire(1000 + HuntWatchdog::kStaleAfterMs));
}

TEST(HuntWatchdog, FreshCqRefreshesStaleTimerButHardTimeoutStillStopsCalling) {
    HuntWatchdog watchdog;
    watchdog.start("YV6BXN", 0);
    watchdog.observe("YV6BXN", 25000);

    EXPECT_FALSE(watchdog.shouldExpire(30000));
    EXPECT_FALSE(watchdog.shouldExpire(HuntWatchdog::kHardTimeoutMs - 1));
    EXPECT_TRUE(watchdog.shouldExpire(HuntWatchdog::kHardTimeoutMs));
}

TEST(HuntWatchdog, EngagedQsoIsNeverExpiredByHuntWatchdog) {
    HuntWatchdog watchdog;
    watchdog.start("9Y4C", 0);
    watchdog.engage("9Y4C");

    EXPECT_TRUE(watchdog.engaged());
    EXPECT_FALSE(watchdog.shouldExpire(10 * HuntWatchdog::kHardTimeoutMs));
}

TEST(HuntWatchdog, OtherStationsCannotRefreshActiveTarget) {
    HuntWatchdog watchdog;
    watchdog.start("YV6BXN", 0);
    watchdog.observe("PT2OP", 25000);

    EXPECT_TRUE(watchdog.shouldExpire(HuntWatchdog::kStaleAfterMs));
}

TEST(HuntWatchdog, ClearRemovesAllLivenessState) {
    HuntWatchdog watchdog;
    watchdog.start("YV6BXN", 0);
    watchdog.clear();

    EXPECT_FALSE(watchdog.active());
    EXPECT_FALSE(watchdog.engaged());
    EXPECT_TRUE(watchdog.call().empty());
    EXPECT_FALSE(watchdog.shouldExpire(1000000));
}
