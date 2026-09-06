#include "Ft8SlotClock.h"
#include <array>

namespace dxw {

bool Ft8SlotClock::isDecisionSecond(int s) noexcept {
    const int second = ((s % 60) + 60) % 60;
    return second == 2 || second == 17 || second == 32 || second == 47;
}

int Ft8SlotClock::millisecondsToNextDecision(int utcSecond, int millisecond) noexcept {
    const int now = (((utcSecond % 60) + 60) % 60) * 1000 + millisecond;
    constexpr std::array<int, 4> points{2000, 17000, 32000, 47000};
    for (int point : points) if (point > now) return point - now;
    return 62000 - now;
}

} // namespace dxw
