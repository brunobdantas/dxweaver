#pragma once

namespace dxw {

class Ft8SlotClock final {
public:
    static bool isDecisionSecond(int utcSecond) noexcept;
    static int millisecondsToNextDecision(int utcSecond, int millisecond) noexcept;
};

} // namespace dxw
